# HTTP API reference

DeckBridge exposes two HTTP surfaces on port 7878:

1. **Session-authenticated UI API** — used by the SvelteKit web UI.
   Cookie-based session after login. Not designed for third-party
   automation, but stable enough that scripts that mind the cookie can
   use it.
2. **Token-authenticated inbound webhook** — designed for other LAN
   apps that want to update a key's state without speaking MQTT.
   Bearer token issued in **Settings → Inbound webhook token**;
   rotate any time.

The OpenAPI schema served at `http://<host>:7878/openapi.json` is
the authoritative reference; an interactive Swagger UI is at
`http://<host>:7878/docs`. This document covers the surfaces a typical
integrator cares about.

## Authentication

### Session cookie (UI API)

```
POST /api/login
Content-Type: application/json

{"password": "<your admin password>"}
```

Sets a signed session cookie. All subsequent UI-API endpoints require
that cookie. `POST /api/logout` clears it.

### Bearer token (inbound webhook)

Generate a token in the web UI: **Settings → Inbound webhook token →
Generate token**. The plaintext is shown once; only the SHA-256 hash
is stored. Rotate any time; the old token immediately stops working.

```
Authorization: Bearer <token>
```

This token is *only* accepted by the inbound state webhook (below);
it does not unlock the rest of the API.

## Inbound state webhook

The primary integration point for non-MQTT clients. Pushes a state
value into a specific key as if it had arrived on the MQTT state topic
(emits the same internal `KeyStateUpdated` event; the painter
re-renders identically).

```
POST /api/pages/{page_id}/keys/{slot}/state
Authorization: Bearer <token>
Content-Type: application/json

{"value": "ON"}
```

Three payload shapes are accepted; `Content-Type` is sniffed:

| Content-Type             | Body example          | Resolved value |
| ------------------------ | --------------------- | -------------- |
| `application/json`       | `{"value": "ON"}`     | `ON`           |
| `application/json`       | `{"state": "ON"}`     | `ON` (alias)   |
| `text/plain` (or any other text) | `ON`          | `ON`           |

Whitespace around the value is trimmed.

Responses:

| Status | Meaning                                    |
| ------ | ------------------------------------------ |
| 200    | `{"ok": true, "value": "<resolved>"}`      |
| 400    | Empty or unparseable body                  |
| 401    | Missing or invalid bearer token            |
| 404    | Page or key not found                      |

The 401 responds identically whether the page/key exists, to avoid
leaking which IDs are valid to an unauthenticated caller.

### curl example

```bash
TOKEN="paste-from-settings"
PAGE="01HZ..."     # page id from the editor URL
SLOT="0"
curl -sS -X POST "http://deckbridge.lan:7878/api/pages/${PAGE}/keys/${SLOT}/state" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value":"ON"}'
```

## UI API endpoints (high level)

All require the session cookie. Full schemas live in
`/openapi.json`.

| Group          | Endpoints                                                                 |
| -------------- | ------------------------------------------------------------------------- |
| Setup wizard   | `GET /api/setup/needed`, `POST /api/setup/complete`                       |
| Auth           | `POST /api/login`, `POST /api/logout`                                     |
| Status         | `GET /api/status` — version, broker state, attached decks                 |
| Pages          | `GET/POST /api/pages`, `GET/PATCH/DELETE /api/pages/{id}`                 |
| Keys           | `GET/PUT/DELETE /api/pages/{id}/keys/{slot}`, `POST .../test-press`       |
| Icons          | `GET/POST /api/icons`, `GET /api/icons/{id}`, `GET /api/icons/{id}/raw`, `DELETE /api/icons/{id}` |
| Settings       | `GET/PATCH /api/settings`, `POST /api/settings/password`, `POST /api/settings/token` |
| Backup/restore | `POST /api/config/export`, `POST /api/config/import`                      |
| Diagnostics    | `WebSocket /ws` — log + event stream (see below)                          |

## Diagnostics WebSocket

```
WebSocket: ws://<host>:7878/ws
```

Requires the same session cookie as the UI API. Unauthenticated
handshakes are closed with code `1008` (policy violation).

On connect, the server sends a catch-up snapshot of the most recent
log records (one frame per record), then streams new log records and
selected lifecycle events as they happen.

Every frame is a single JSON object on its own line:

```json
{"kind": "log",   "record": "<rendered structlog json string>"}
{"kind": "event", "type": "DeckConnected", "payload": {"serial": "AL...", "model": "Stream Deck MK.2"}}
```

The `record` field is the daemon's structured log line as a string —
parse it again to access individual fields. The `event` channel
currently emits four event types: `DeckConnected`, `DeckDisconnected`,
`BrokerConnected`, `BrokerDisconnected`. Slow consumers are dropped
silently rather than back-pressuring the daemon.

## Backup and restore

```
POST /api/config/export    # → 200, full Snapshot JSON
POST /api/config/import    # body: Snapshot JSON, → 200, replays Snapshot
```

Both require the session cookie. The Snapshot includes preferences,
decks, pages, keys, and icon metadata. **Uploaded icon bytes are NOT
included** — see [Configuration → Backup and restore](configuration.md#backup-and-restore)
for the caveat and the full-binary backup workaround.

## Versioning

The HTTP API is versioned implicitly with the daemon. v1.x ships with
the surface documented above; breaking changes will require a major
version bump. The `version` field in `GET /api/status` reports the
running daemon's version so a client can refuse to talk to an
unfamiliar release.
