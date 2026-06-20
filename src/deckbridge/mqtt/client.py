"""MqttClient — aiomqtt-backed broker connection with automatic reconnect.

Lifecycle owned by the FastAPI lifespan. The client runs a single asyncio
task that:

    1. reads the broker config from a fresh :class:`Preferences` snapshot
    2. opens an :class:`aiomqtt.Client` context
    3. fires :class:`BrokerConnected`, drains queued publishes, processes
       incoming messages
    4. on disconnect or error, fires :class:`BrokerDisconnected` and
       reconnects with exponential backoff (1s → 60s)
    5. exits cleanly when ``stop()`` is called

Subscribers and queued publishes survive across reconnects — re-subscribed
on every fresh connection, queued publishes flushed when ready. This means
callers can ``publish()`` even before the broker is reachable; the message
sits in memory until the connection is up.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl
from typing import TYPE_CHECKING, Any

import aiomqtt

from deckbridge.events.types import BrokerConnected, BrokerDisconnected
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from deckbridge.events import EventBus
    from deckbridge.storage.schema import Preferences

PrefsProvider = "Callable[[], Preferences]"
SubscriberHandler = "Callable[[str, bytes], Awaitable[None]]"

# Backoff bounds for the reconnect loop (seconds).
_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 60.0


class MqttClient:
    """Long-lived MQTT connection with reconnect, queued publish, and pub/sub fan-out.

    Designed to be constructed once and started during FastAPI lifespan
    startup. Methods are safe to call from any coroutine on the same event
    loop the client was started on.
    """

    def __init__(self, bus: EventBus, prefs_provider: Callable[[], Preferences]) -> None:
        self._bus = bus
        self._prefs_provider = prefs_provider

        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        # Signal a config change so the connect loop tears down and re-reads.
        self._reload = asyncio.Event()

        self._client: aiomqtt.Client | None = None
        self._connected = False

        # Topics → ordered list of handlers. Each handler receives (topic, payload).
        self._subscribers: dict[str, list[Callable[[str, bytes], Awaitable[None]]]] = {}
        # Outbound publishes buffered while disconnected.
        self._publish_queue: asyncio.Queue[tuple[str, bytes, bool, int]] = asyncio.Queue()
        # Strong refs to fire-and-forget background subscribe tasks so they
        # aren't garbage-collected before they get scheduled.
        self._bg_tasks: set[asyncio.Task[None]] = set()

        self._log = get_logger(__name__)

    # ---- public API -----------------------------------------------------

    @property
    def connected(self) -> bool:
        """True when an aiomqtt session is currently open."""
        return self._connected

    @property
    def configured(self) -> bool:
        """True when the user has set a broker host in preferences."""
        return bool(self._prefs_provider().mqtt_host)

    def start(self) -> None:
        """Begin the connect/reconnect loop. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._reload.clear()
        self._task = asyncio.create_task(self._run(), name="deckbridge-mqtt")

    async def stop(self) -> None:
        """Cleanly tear the connection down. Safe to call when not started."""
        self._stopping.set()
        self._reload.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def reload(self) -> None:
        """Signal the connect loop to re-read preferences and reconnect.

        Use after the user changes broker config via the settings API.
        """
        self._reload.set()

    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Queue a message for publication on the broker.

        If the client isn't currently connected, the message is buffered and
        sent on the next successful connection.
        """
        body = payload.encode("utf-8") if isinstance(payload, str) else payload
        await self._publish_queue.put((topic, body, retain, qos))

    def subscribe(self, topic: str, handler: Callable[[str, bytes], Awaitable[None]]) -> None:
        """Register *handler* to receive every message on *topic*.

        The subscription survives reconnects (re-subscribed on every fresh
        connection). Multiple handlers may share a topic; all are invoked
        for each message.
        """
        self._subscribers.setdefault(topic, []).append(handler)
        # If we're currently connected, subscribe immediately on the live
        # client; otherwise it'll be picked up when the next session opens.
        if self._client is not None and self._connected:
            task = asyncio.create_task(self._safe_subscribe(self._client, topic))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    def unsubscribe(self, topic: str, handler: Callable[[str, bytes], Awaitable[None]]) -> None:
        """Best-effort removal of a subscriber. Idempotent."""
        handlers = self._subscribers.get(topic)
        if handlers is None:
            return
        with contextlib.suppress(ValueError):
            handlers.remove(handler)
        if not handlers:
            self._subscribers.pop(topic, None)
            # Note: we don't actively unsubscribe from the broker — harmless,
            # just slightly chattier. A future optimization can.

    # ---- main loop ------------------------------------------------------

    async def _run(self) -> None:
        backoff = _BACKOFF_INITIAL
        while not self._stopping.is_set():
            prefs = self._prefs_provider()
            if not prefs.mqtt_host:
                # Nothing to connect to — wait for either a stop or a config
                # reload (set when settings PATCH lands).
                self._log.info("mqtt_no_host_configured")
                await self._wait_for_event_or_stop(self._reload, timeout=None)
                self._reload.clear()
                continue

            self._log.info(
                "mqtt_connecting",
                host=prefs.mqtt_host,
                port=prefs.mqtt_port,
                tls=prefs.mqtt_tls,
            )
            try:
                async with self._open_client(prefs) as client:
                    self._client = client
                    self._connected = True
                    backoff = _BACKOFF_INITIAL
                    await self._bus.publish(BrokerConnected(host=prefs.mqtt_host))

                    # Re-subscribe to every topic we know about.
                    for topic in list(self._subscribers):
                        await self._safe_subscribe(client, topic)

                    await self._session(client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log.warning("mqtt_session_error", error=repr(exc))
            finally:
                if self._connected:
                    self._connected = False
                    await self._bus.publish(BrokerDisconnected())
                self._client = None

            if self._stopping.is_set():
                break

            # Backoff before the next attempt; reload short-circuits the wait.
            await self._wait_for_event_or_stop(self._reload, timeout=backoff)
            self._reload.clear()
            backoff = min(backoff * 2, _BACKOFF_MAX)

    def _open_client(self, prefs: Preferences) -> aiomqtt.Client:
        kwargs: dict[str, Any] = {
            "hostname": prefs.mqtt_host,
            "port": prefs.mqtt_port,
        }
        if prefs.mqtt_username:
            kwargs["username"] = prefs.mqtt_username
        if prefs.mqtt_password:
            kwargs["password"] = prefs.mqtt_password
        if prefs.mqtt_tls:
            kwargs["tls_context"] = ssl.create_default_context()
        return aiomqtt.Client(**kwargs)

    async def _session(self, client: aiomqtt.Client) -> None:
        """Run the publish drain and incoming-message loop concurrently.

        Either coroutine raising tears the session down for a reconnect.
        """
        publish_task = asyncio.create_task(self._publish_loop(client))
        receive_task = asyncio.create_task(self._receive_loop(client))
        reload_waiter = asyncio.create_task(self._reload.wait())
        stop_waiter = asyncio.create_task(self._stopping.wait())
        try:
            done, _ = await asyncio.wait(
                {publish_task, receive_task, reload_waiter, stop_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in done:
                if t in (publish_task, receive_task) and t.exception():
                    raise t.exception()  # type: ignore[misc]
        finally:
            for t in (publish_task, receive_task, reload_waiter, stop_waiter):
                if not t.done():
                    t.cancel()
            for t in (publish_task, receive_task, reload_waiter, stop_waiter):
                with contextlib.suppress(asyncio.CancelledError, BaseException):
                    await t

    async def _publish_loop(self, client: aiomqtt.Client) -> None:
        while True:
            topic, payload, retain, qos = await self._publish_queue.get()
            try:
                await client.publish(topic, payload=payload, qos=qos, retain=retain)
            except Exception as exc:
                # Re-queue and let the outer reconnect kick in.
                await self._publish_queue.put((topic, payload, retain, qos))
                raise RuntimeError(f"publish failed: {exc!r}") from exc

    async def _receive_loop(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            topic = str(message.topic)
            payload = (
                bytes(message.payload)
                if isinstance(message.payload, (bytes, bytearray))
                else str(message.payload).encode("utf-8")
            )
            handlers = list(self._subscribers.get(topic, ()))
            for handler in handlers:
                try:
                    await handler(topic, payload)
                except Exception as exc:
                    self._log.warning(
                        "mqtt_handler_failed",
                        topic=topic,
                        handler=getattr(handler, "__qualname__", repr(handler)),
                        error=repr(exc),
                    )

    async def _safe_subscribe(self, client: aiomqtt.Client, topic: str) -> None:
        try:
            await client.subscribe(topic)
            self._log.info("mqtt_subscribed", topic=topic)
        except Exception as exc:
            self._log.warning("mqtt_subscribe_failed", topic=topic, error=repr(exc))

    async def _wait_for_event_or_stop(self, event: asyncio.Event, *, timeout: float | None) -> None:
        """Wait for *event* or self._stopping, whichever fires first."""
        ev_task = asyncio.create_task(event.wait())
        stop_task = asyncio.create_task(self._stopping.wait())
        try:
            await asyncio.wait(
                {ev_task, stop_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for t in (ev_task, stop_task):
                if not t.done():
                    t.cancel()
            for t in (ev_task, stop_task):
                with contextlib.suppress(asyncio.CancelledError):
                    await t
