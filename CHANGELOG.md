# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-05-10

Minor release — five new per-key presentation options requested during
v1.0.1 testing. All defaults preserve v1.0.1 rendering byte-for-byte;
existing keys upgrade in place with no behavior change.

### Added

- **`Key.show_icon` / `Key.show_label`** (bool, default `true`). When
  false, the painter skips drawing that element. The stored
  `label`/`icon_id` values are preserved across toggles. With
  `show_icon = false` the label is centered vertically rather than
  bottom-anchored, matching the "label-only key" expectation.
- **`Key.bg_color`** (hex `#RRGGBB`, default `"#000000"`). Solid
  background drawn under the icon. v1.0 always painted black.
- **`Key.bg_image_id`** (icon-library id, optional). A user-uploaded
  image cover-fitted (scale-to-fill, center-crop) over the bg color
  and under the icon. Reuses the existing icon upload system — pick
  an uploaded PNG via the same picker used for foreground icons.
- **`Key.label_color`** (hex `#RRGGBB`, default `"#FFFFFF"`).
  Previously hard-coded white.
- **`Key.icon_color`** (hex or `null`, default `null`). When set, each
  pixel of the icon's RGB is multiplied by this color (alpha
  preserved). Pure white icons (the bundled Lucide set) become exactly
  the tint color; uploaded colored icons get shifted toward it.

### Editor UI

The KeyEditor's right-hand panel grew a "Background" section (color +
image picker + clear), per-element "Show" checkboxes for icon and
label, and `<input type="color">` controls for label color and the
optional icon tint.

### Schema/wire format

No migration needed. The keys table is a JSON-blob column; Pydantic's
field defaults handle backwards compat for keys persisted before this
release.

## [1.0.1] — 2026-05-10

Patch release — first round of real-world Pi testing surfaced four
fixable bugs and a small papercut. No data migrations; the wire and
storage formats are unchanged.

### Added

- **Per-key padding setting** (`Key.padding`, range 0–20). Adds extra
  inset around the icon and label. Useful for Lucide icons that feel
  cropped against the key edge. Default 0 preserves v1.0.0 rendering
  byte-for-byte; existing keys without the field deserialize at 0.
  Surfaced in the editor as a paired range slider + number input.

### Fixed

- **`KeyEditor` could not load already-saved keys**: `structuredClone`
  on the `initial` prop threw `Proxy object could not be cloned`
  (Svelte 5 wraps every prop in a reactive Proxy). Switched to
  `$state.snapshot()` which is the canonical Svelte 5 unwrap idiom.
  Empty slots already worked because they fell back to a plain
  `emptyKey()` template.
- **Stream Deck displayed the Elgato boot logo forever** when attached
  with no pages configured. `Deck.attach()` now calls `handle.reset()`
  to clear the boot logo so the user sees a known blank state even
  before the painter has anything to render.
- **`scripts/install.sh` did not actually restart the daemon** on
  reinstall: `systemctl enable --now` is a no-op when the service is
  already active, so backend changes never reached the running process.
  Switched to explicit `systemctl restart` after `enable`.
- **`scripts/install.sh` packaged a stale SPA on re-runs**: the previous
  "skip npm build if `web_dist/index.html` already exists" guard meant
  a `git pull` that updated `web/src/` but left `web_dist/` from an
  earlier build silently shipped the old frontend inside the new wheel.
  Always rebuild now (~3 s on a Pi).
- **Shipped scripts were not executable**: `scripts/install.sh`,
  `scripts/uninstall.sh`, and `scripts/build_bundled_assets.py` are now
  committed with the executable bit set so fresh clones don't need
  `chmod +x` first.

## [1.0.0] — 2026-05-10

First stable release. Feature-complete for the Elgato Stream Deck MK.2
hardware target.

### Added

- **Daemon scaffold (M0–M1)**: Python 3.11 + FastAPI + structlog,
  pluggable storage (SQLite default, JSON files alternative) with
  parity-tested behavior, settings via env-var prefixed `DECKBRIDGE_`.
- **Event bus (M2)**: in-process pub/sub decoupling press dispatch,
  state subscription, image rendering, and HA discovery.
- **Stream Deck integration (M3)**: pyudev hot-plug + the `streamdeck`
  library; supports MK.2 (verified) and other Elgato models recognized
  by the udev rules.
- **Web UI (M4–M5)**: SvelteKit 2 / Svelte 5 SPA with first-run setup
  wizard, login, editor (live deck preview, key panel, page management,
  icon picker), and settings page. Built into static assets and served
  by the daemon.
- **MQTT (M6)**: `aiomqtt` client with reconnect/backoff, queued
  publish, per-key subscriptions. JMESPath state extraction. Press
  dispatcher routes to MQTT publish, HTTP webhook, page switch, or
  no-op. Image-renderer + painter cache.
- **Home Assistant Discovery + inbound webhook (M7)**: device-trigger
  entities auto-published per key; bearer-token-protected
  `POST /api/pages/{page_id}/keys/{slot}/state` for non-MQTT clients.
- **Diagnostics + backup (M8)**: log ringbuffer feeding a
  session-authenticated `WebSocket /ws` for live tail; whole-config
  export/import via `POST /api/config/{export,import}`. Diagnostics
  tab in the web UI surfaces logs + recent device/broker events.
- **Bundled assets**: ~85 Lucide icons pre-rendered to MK.2-native
  72×72 px PNG; Inter font (Regular + Bold) bundled for offline UI use.
- **Packaging (M9)**: Docker multi-stage image + compose file with USB
  passthrough; bare-metal `scripts/install.sh` provisioning a venv at
  `/opt/deckbridge`, system user, udev rules, and a hardened systemd
  unit. The installer also runs `npm ci && npm run build` against the
  bundled `web/` directory so a fresh git clone produces a working
  SPA without a separate manual build step. `scripts/uninstall.sh`
  with a `--purge` flag to optionally wipe user data.
- **Documentation (M10)**: install / configuration / MQTT / Home
  Assistant / HTTP API guides under `docs/`; OpenAPI schema served at
  `/openapi.json` with Swagger UI at `/docs`.

### Security

- Argon2id password hashing for the admin password.
- Itsdangerous-signed session cookies; secret persisted at
  `${DECKBRIDGE_DATA_DIR}/secrets/session.key` if not provided via env.
- Constant-time SHA-256 comparison for the inbound bearer token; only
  the hash is stored, plaintext is shown once at rotation.
- WebSocket handshake refused with code 1008 if unauthenticated.
- Systemd unit enforces NoNewPrivileges, ProtectSystem=strict,
  ProtectHome, and friends; runs as a dedicated unprivileged user in
  the `plugdev` group.

### Known limitations

- v1 supports a single primary deck in the UI. The daemon handles
  multiple decks plugged in concurrently, but the editor surfaces only
  the first.
- Web UI is HTTP-only (no TLS in v1). Use a reverse proxy if you need
  HTTPS.
- Config export does not include the bytes of user-uploaded icons —
  only their metadata. Take a filesystem-level backup of
  `${DECKBRIDGE_DATA_DIR}` if you need a true binary backup.
- Multi-CA / client-cert MQTT auth is not configurable from the UI in
  v1; basic TLS to a server with a system-trusted CA does work.
