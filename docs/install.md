# Installation

DeckBridge ships two install paths in v1, both targeting Linux. The bare-metal
script is the recommended path on a Raspberry Pi; Docker is recommended
elsewhere or for users who already run their home stack in containers.

Both paths require:

- a Linux host (Raspberry Pi OS, Debian, or Ubuntu — anything apt-based)
- a connected Elgato Stream Deck MK.2 (other models work but are unverified)
- network access to an MQTT broker on your LAN
  (Home Assistant's bundled Mosquitto add-on works fine)

## Option A — bare-metal install script (recommended on a Pi)

```bash
git clone https://git.senal.dev/Senal/DeckBridge.git
cd DeckBridge
sudo ./scripts/install.sh
```

The script:

1. installs apt dependencies (`python3-venv`, `libhidapi-libusb0`,
   `libudev1`, `libusb-1.0-0`)
2. creates a `deckbridge` system user in the `plugdev` group
3. installs DeckBridge into a venv at `/opt/deckbridge/venv`
4. drops the udev rules from `scripts/udev/99-streamdeck.rules` to
   `/etc/udev/rules.d/` so the service user can talk to the deck
   without root
5. installs and enables `deckbridge.service` (systemd)
6. prints the URL of the first-run setup wizard

It is safe to re-run the installer to upgrade in place. User data in
`/var/lib/deckbridge` and `/etc/deckbridge` is preserved across reinstalls.

### Verifying the service

```bash
systemctl status deckbridge.service
journalctl -u deckbridge -f
```

Then open `http://<pi-ip>:7878` in a browser to run the setup wizard.

## Option B — Docker

```bash
git clone https://git.senal.dev/Senal/DeckBridge.git
cd DeckBridge
docker compose -f docker/docker-compose.yml up -d --build
```

Then visit `http://<host>:7878`.

The compose file:

- mounts `/dev/bus/usb` into the container for Stream Deck access
- persists state in a named volume (`deckbridge-data`) at `/data`
- defaults the broker host to `host.docker.internal` (override via
  `DECKBRIDGE_MQTT_HOST` in the environment)

### USB passthrough notes

The compose file uses `/dev/bus/usb:/dev/bus/usb`, which works on most
desktop Linux hosts. On hosts where this is the wrong path (some
appliance OSes, some NAS setups) you'll need to substitute the specific
`/dev/hidraw*` device or use a `device_cgroup_rules` entry that matches
your kernel's exposed nodes. To find the right node:

```bash
ls -l /dev/hidraw*
udevadm info -a -n /dev/hidrawN | grep -E 'idVendor|idProduct'
# Elgato vendor: 0fd9, MK.2 product: 0080
```

If your container runtime doesn't surface USB devices at all (rootless
Podman in some configurations, certain Kubernetes setups), the
bare-metal install path is the simpler answer.

### Bundled Mosquitto (optional)

The compose file ships a commented `mosquitto` service. Uncomment it
(and the `depends_on` block) to run a broker alongside DeckBridge.
Most users should point at their existing Home Assistant /
Zigbee2MQTT broker instead.

## File locations

| Purpose                        | Bare-metal                                    | Docker                                |
| ------------------------------ | --------------------------------------------- | ------------------------------------- |
| Editable config (rare)         | `/etc/deckbridge/`                            | `/data/` (inside container)           |
| SQLite DB / cache / icons      | `/var/lib/deckbridge/`                        | `/data/` (named volume)               |
| Install dir                    | `/opt/deckbridge/`                            | (in image)                            |
| Service unit                   | `/etc/systemd/system/deckbridge.service`      | n/a (managed by `docker compose`)     |
| udev rule                      | `/etc/udev/rules.d/99-streamdeck.rules`       | (host-side, install rule manually)    |
| Logs                           | `journalctl -u deckbridge`                    | `docker logs deckbridge`              |

The web UI is the only interface you should normally need; the
on-disk layout is documented for backup and curiosity. See
[Configuration](configuration.md) for what's stored where.

## Upgrading

### Bare-metal

```bash
cd DeckBridge
git pull
sudo ./scripts/install.sh
```

The installer detects the existing venv and reinstalls in place; the
systemd unit is restarted automatically.

### Docker

```bash
cd DeckBridge
git pull
docker compose -f docker/docker-compose.yml up -d --build
```

## Uninstalling

### Bare-metal

```bash
sudo ./scripts/uninstall.sh           # keep config and data
sudo ./scripts/uninstall.sh --purge   # also wipe data and the service user
```

The default mode preserves `/var/lib/deckbridge` and `/etc/deckbridge`
so a later reinstall picks up where you left off.

### Docker

```bash
docker compose -f docker/docker-compose.yml down
docker volume rm deckbridge_deckbridge-data   # wipe data
```

## Troubleshooting

- **The deck isn't detected after install.** Re-plug the device, then
  check `journalctl -u deckbridge -f` for an `attached` event. If you
  installed via the script and the user didn't pick up the udev rule,
  unplug-replug or reboot the Pi.
- **Web UI says "broker not connected".** Settings → MQTT broker. The
  daemon retries with backoff; the diagnostics tab shows the latest
  reconnect attempt.
- **Permission denied on `/dev/hidraw*` (Docker).** Re-check the
  passthrough notes above; you may need to specify the device node
  directly instead of `/dev/bus/usb`.

If you're stuck, the [Diagnostics tab](configuration.md#diagnostics)
in the web UI shows live logs and recent device/broker events — paste
that into a GitHub issue.
