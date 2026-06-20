# MQTT integration

DeckBridge requires an external MQTT broker. It does not run one
in-process. (See [Installation](install.md#bundled-mosquitto-optional)
for the optional bundled-Mosquitto path if you don't already have a
broker on your LAN.)

## How a key uses MQTT

Each key configures up to two independent MQTT touchpoints:

1. **Press** (outbound). On physical press, publish a payload to a
   topic. Configure topic, payload, QoS, and retain flag.
2. **State** (inbound). Subscribe to a topic; when a message arrives,
   re-render the key with a state-specific icon. Configure topic,
   optional JMESPath extractor, and a state→icon map.

The two are independent: a key can be press-only (a momentary action),
state-only (a status indicator), both (a toggle that reflects external
state), or neither (a page-switch button or no-op placeholder).

## State extraction with JMESPath

Most MQTT payloads on a real broker are either bare strings (`ON`/`OFF`)
or small JSON objects with a state field nested somewhere inside.
DeckBridge uses [JMESPath](https://jmespath.org/) — the same syntax
Home Assistant uses for templating — to extract a single value from
each incoming message before matching it against your state map.

| Topic payload                          | JMESPath        | Extracted value |
| -------------------------------------- | --------------- | --------------- |
| `ON`                                   | _(empty)_       | `ON`            |
| `{"state":"on","brightness":120}`      | `state`         | `on`            |
| `{"power":{"value":"OFF"}}`            | `power.value`   | `OFF`           |
| `{"events":[{"type":"motion"}]}`       | `events[0].type`| `motion`        |

If the JMESPath query fails or returns `null`, the daemon logs a
debug-level warning and the key falls back to its default icon. This
is the desired behavior for transient malformed messages — bad data
shouldn't blank your deck.

## Press payloads

The press dispatcher publishes whatever payload you've configured
verbatim. There is no templating; if you need to publish JSON, write
the JSON literally. Examples:

| Use case                        | Topic                                  | Payload          |
| ------------------------------- | -------------------------------------- | ---------------- |
| Toggle a Z2M switch             | `zigbee2mqtt/desk_lamp/set`            | `{"state":"TOGGLE"}` |
| Trigger a HA automation         | `deckbridge/keys/lamp/press`           | `pressed`        |
| Mute via a custom service       | `home/audio/mute`                      | `{"on":true}`    |

If you need rich templating (variables, computed values), publish a
trigger event from DeckBridge and respond to it with a Home Assistant
or Node-RED automation that does the templating.

## Topic conventions

DeckBridge does not impose a topic structure on your broker. Use
whatever your existing devices already publish to. If you want a clean
namespace for DeckBridge-driven actions, a common pattern is:

```
deckbridge/<deck-serial>/key/<n>/press
deckbridge/<deck-serial>/key/<n>/state
```

…but you can use anything. The MK.2's deck serial is shown in the web
UI under **Diagnostics → Daemon → Attached decks**.

## Reconnect behavior

The MQTT client connects on daemon startup and reconnects with
exponential backoff if the broker drops the connection. Backoff caps
at ~30 seconds between attempts. On successful reconnect:

- All key subscriptions are re-established.
- Home Assistant Discovery payloads are re-published (they're idempotent).
- Already-cached state from before the disconnect is retained — keys
  do not blank to their default icon during a temporary broker outage.

The **Diagnostics** tab surfaces the last `BrokerConnected` /
`BrokerDisconnected` event so you can confirm the daemon is talking to
your broker without tailing logs.

## TLS

Toggle TLS on in **Settings → MQTT broker** if your broker uses
mqtts://. The daemon uses the system trust store by default. v1 does
not support custom CA certificates or client-cert auth; if you need
either, file an issue.

## Quality-of-Service and retention

- **Press publishes**: configured per-key. Default QoS=0, retain=false.
  Most use-cases (button presses) want fire-and-forget; bump to QoS=1
  if you need at-least-once delivery and your broker is on a flaky
  link.
- **State subscriptions**: subscribe with QoS=0. Retained messages on
  the topic are delivered immediately on subscribe, which means
  DeckBridge picks up the current state of any device that publishes
  retained, without you having to wait for the next state change.

## Home Assistant Discovery

When enabled in **Settings**, DeckBridge announces each key under the
`homeassistant/device_automation/...` topic prefix so HA picks them up
as device-trigger entities automatically. See
[Home Assistant integration](home-assistant.md) for the payload shape
and example automations.
