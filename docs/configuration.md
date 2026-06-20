# Configuration

DeckBridge is configured exclusively through the web UI. There is no
expectation that you hand-edit YAML or SQLite — but the on-disk format
is documented here for backup, migration, and curiosity.

## First-run setup wizard

When the daemon starts with no preferences row in storage, every HTTP
request is redirected to `/setup`. The wizard collects:

1. **Admin password.** Used to log into the web UI. Stored as an
   argon2id hash; the plaintext is never persisted.
2. **MQTT broker.** Host, port, optional username/password, optional TLS.
   You can change all of this later in **Settings**.

After completing the wizard you're dropped on the editor with whatever
deck is plugged in pre-selected.

## What gets configured

- **Decks.** One or more connected Stream Decks. v1 UI assumes one
  primary deck; the daemon supports several plugged in at once and
  associates pages with a specific serial.
- **Pages.** Multiple per deck. A page-switch action type lets keys
  jump between pages — a pattern for grouping related buttons (e.g.
  "Lights", "Music", "Scenes").
- **Keys.** 15 per page on the MK.2 (5×3 grid). Each key configures:
  - **Press action.** MQTT publish, HTTP webhook, page switch, or no-op.
  - **State subscription.** MQTT topic + optional JMESPath extractor +
    value→icon mapping. Re-renders the key when state changes.
  - **Icons.** One per state value, plus a default. Sourced from the
    bundled Lucide set or your own uploads.
- **Settings.** Broker connection, Home Assistant Discovery toggle,
  password, API token, storage backend, port.

## Storage backends

You choose between two storage backends at install time (env var
`DECKBRIDGE_STORAGE_BACKEND`, defaults to `sqlite`):

- **SQLite** (default) — a single `data.db` at
  `${DECKBRIDGE_DATA_DIR}/data.db`. Compact, fast, single-file backup.
- **Files** — JSON files under `${DECKBRIDGE_DATA_DIR}/store/` plus
  uploaded icon PNGs. Friendlier to git/version-control if you want to
  track config changes over time.

Both backends share the same Pydantic schema (the `Snapshot` model used
by the export/import endpoints), so switching backends is non-destructive:

```bash
deckbridge migrate --to files     # or --to sqlite
# then update DECKBRIDGE_STORAGE_BACKEND in /etc/systemd/system/...
sudo systemctl restart deckbridge.service
```

## Backup and restore

The web UI's **Settings → Backup & restore** section serves and accepts
a single JSON document containing decks, pages, keys, icon metadata,
and preferences (including the password and API-token hashes — treat
the export file as a secret).

The same surface is exposed via the HTTP API:

```
POST /api/config/export   # returns the snapshot JSON (auth required)
POST /api/config/import   # replaces all stored config with the supplied snapshot
```

**Important caveat:** the export does NOT include the bytes of icons
that you uploaded yourself. The icon's *metadata record* (id, name,
source, content-hash reference) round-trips, but the underlying PNG on
disk does not. If you restore an export onto a fresh install, any keys
that referenced uploaded icons will render blank until you re-upload
the same files. Bundled-icon references (`lucide:*`) round-trip
cleanly because the bytes ship with the daemon.

If you need a true binary backup (icons included), back up the
contents of `${DECKBRIDGE_DATA_DIR}` directly:

```bash
sudo tar czf deckbridge-$(date +%F).tar.gz -C /var/lib deckbridge
```

## Diagnostics

The **Diagnostics** tab in the web UI shows:

- Daemon status: version, broker connection, attached decks
- A live tail of the structured log stream (same records as
  `journalctl -u deckbridge -f`, but in the browser)
- A timeline of recent deck-attached/detached and broker-connect events

Useful when filing a bug report — copy a relevant log slice and paste it
into the issue.

## API token rotation

Some external apps prefer HTTP over MQTT. The web UI's **Settings →
Inbound webhook token** generates a bearer token that grants access to
`POST /api/keys/{id}/state` (see [API reference](api.md)). Rotation
always invalidates the previous token; only the newest token is valid.
