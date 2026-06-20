# DeckBridge

> A self-hosted bridge that turns a USB Stream Deck into a network-accessible smart-button surface for your LAN.

DeckBridge runs on a Raspberry Pi (or any Linux box), reads input from a
connected Elgato Stream Deck, and exposes each key as a smart button
over **MQTT** and **HTTP**. A web interface handles configuration,
page management, icon graphics, and live state-driven re-rendering —
no config files to edit.

**Status:** v1.0 — feature-complete for the MK.2 (15-key) hardware
target.

## Features

- **Web-based configuration.** First-run wizard sets up your password
  and MQTT broker; the editor shows a live preview of the deck and
  lets you assign press actions, state subscriptions, and icons per
  key.
- **Multiple pages per deck.** A page-switch action type lets keys
  jump between contexts (e.g. "Lights", "Music", "Scenes").
- **Bundled icon library + uploads.** ~85 Lucide icons ship with the
  daemon at MK.2-native 72×72 px, plus you can upload your own PNGs.
- **MQTT-first integration.** Each key publishes on press; subscribes
  to a state topic and re-renders its icon when the value changes.
  JMESPath extractors handle nested JSON payloads.
- **HTTP webhooks (outbound and inbound).** Per-key webhook actions
  for non-MQTT services; bearer-token-protected `/api/keys/{id}/state`
  endpoint for tools that prefer HTTP both ways.
- **Home Assistant MQTT Discovery.** Each key auto-announces as a
  device-trigger entity — wire automations from the HA UI without YAML.
- **Live diagnostics tab.** Browser-based log tail and event timeline
  over a session-authenticated WebSocket; no need to SSH in for
  routine troubleshooting.
- **Backup and restore.** Export the entire config (decks/pages/keys/
  preferences) as a single JSON file from Settings; import to roll back
  or move to a new install.
- **Two install paths.** Bare-metal systemd installer for Pi
  (recommended) and Docker compose for everything else.

## Hardware support

- **Elgato Stream Deck MK.2** (15-key, 5×3 grid, 72×72 px keys) — the
  v1 supported target.
- Other Stream Deck models (Original, XL, Mini, +, Neo, Pedal) are
  recognized by the udev rules and the daemon will likely run, but
  v1's UI assumes the MK.2 layout. Multi-model support is planned for
  post-1.0.

## Quick start

### On a Raspberry Pi (recommended)

```bash
git clone https://git.senal.dev/Senal/DeckBridge.git
cd DeckBridge
sudo ./scripts/install.sh
# then visit http://<pi-ip>:7878
```

### Docker

```bash
git clone https://git.senal.dev/Senal/DeckBridge.git
cd DeckBridge
docker compose -f docker/docker-compose.yml up -d --build
# then visit http://<host>:7878
```

First visit launches a setup wizard for password creation and MQTT
broker connection. See [Installation](docs/install.md) for the full
walkthrough including USB passthrough notes, upgrades, and uninstall.

## Documentation

- [Installation](docs/install.md) — Docker, bare-metal, file layout, troubleshooting
- [Configuration](docs/configuration.md) — what gets stored where, backup, diagnostics
- [MQTT integration](docs/mqtt-integration.md) — press/state model, JMESPath, reconnect
- [Home Assistant integration](docs/home-assistant.md) — Discovery payload, example automations
- [HTTP API reference](docs/api.md) — inbound webhook, UI API, WebSocket

## Architecture in one paragraph

A FastAPI daemon (Python 3.11+) runs as a systemd service. It owns the
USB connection to the Stream Deck via the `streamdeck` Python library
and pyudev for hot-plug, an asyncio MQTT client (`aiomqtt`) for broker
I/O, and a structured event bus that decouples the press dispatcher,
state subscriber, image renderer, and HA discovery publisher. Storage
is pluggable (SQLite default, JSON files alternative) behind a single
Pydantic schema. The web UI is a SvelteKit 2 / Svelte 5 SPA built into
static assets and served by FastAPI alongside the JSON API and a
WebSocket for live diagnostics. Auth is a session cookie for the UI
and a separate bearer token for the inbound state webhook.

## Security model

DeckBridge is designed for **trusted LAN deployment only**. The web
UI is HTTP-only (no TLS in v1) and assumes everyone on the network is
trusted. **Do not expose the web UI to the public internet without an
HTTPS-terminating reverse proxy.** The session cookie and bearer
token both go over the wire in the clear without one.

There is no telemetry. The daemon does not phone home, does not
contact any server other than your configured MQTT broker and your
configured HTTP webhooks, and does not require an account anywhere.

## Contributing

Issues and PRs welcome — see the repository's issues tab. The codebase
is fully type-checked (mypy), lint-gated (ruff), and unit + integration
tested (300+ tests, run with `pytest`). The frontend is type-checked
with `svelte-check` and built with Vite.

## Trademark notice

"Elgato" and "Stream Deck" are trademarks of Corsair Memory, Inc.
DeckBridge is an independent open-source project and is not affiliated
with, endorsed by, or sponsored by Corsair or Elgato.

## License

DeckBridge is released under the
[GNU General Public License v3.0 or later](LICENSE). Forks and
derivative works must also be licensed under GPL-3.0+.
