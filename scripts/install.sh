#!/usr/bin/env bash
# DeckBridge bare-metal installer for Raspberry Pi OS / Debian-derived Linux.
#
# Installs DeckBridge into /opt/deckbridge as a systemd service running under
# a dedicated unprivileged user. Most users on a Pi should prefer this over
# Docker because USB passthrough is simpler and the service starts at boot
# with full hardware access via udev rules.
#
# Usage:
#   sudo ./scripts/install.sh
#
# Re-runnable. Existing data in /var/lib/deckbridge and /etc/deckbridge is
# preserved across reinstalls.

set -euo pipefail

INSTALL_DIR=${DECKBRIDGE_INSTALL_DIR:-/opt/deckbridge}
DATA_DIR=${DECKBRIDGE_DATA_DIR:-/var/lib/deckbridge}
CONFIG_DIR=${DECKBRIDGE_CONFIG_DIR:-/etc/deckbridge}
SERVICE_USER=${DECKBRIDGE_SERVICE_USER:-deckbridge}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UDEV_RULE_SRC="${SCRIPT_DIR}/udev/99-streamdeck.rules"
UDEV_RULE_DST="/etc/udev/rules.d/99-streamdeck.rules"
SYSTEMD_UNIT_SRC="${SCRIPT_DIR}/systemd/deckbridge.service"
SYSTEMD_UNIT_DST="/etc/systemd/system/deckbridge.service"

log() { printf '[deckbridge install] %s\n' "$*" >&2; }
die() { printf '[deckbridge install] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "must run as root (try: sudo $0)"
  fi
}

detect_os() {
  if [ ! -f /etc/os-release ]; then
    die "cannot detect OS (no /etc/os-release); only Debian-derived distros supported"
  fi
  # shellcheck source=/dev/null
  . /etc/os-release
  case "${ID_LIKE:-${ID:-}}" in
    *debian*|debian|raspbian|ubuntu) ;;
    *) die "unsupported distro: ${ID:-unknown}. Apt-based (Debian/Ubuntu/Raspbian) only." ;;
  esac
}

install_apt_deps() {
  log "installing apt dependencies"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    libhidapi-libusb0 \
    libudev1 \
    libusb-1.0-0 \
    nodejs \
    npm \
    >/dev/null
}

build_frontend() {
  # The pip install below packages whatever is in src/deckbridge/web_dist/
  # into the wheel. On a fresh git clone that directory is empty (the
  # gitignore excludes build output), so without this step the daemon
  # starts but has no SPA to serve and every UI request 404s.
  #
  # Always rebuild on install — never skip based on "index.html already
  # exists". A stale web_dist (e.g. from a previous build before a `git
  # pull` updated web/src/) silently ships an outdated SPA inside the
  # new wheel, which is the worst kind of bug to debug because the
  # backend version moved but the frontend didn't. The build is a few
  # seconds; correctness wins over speed every time here.
  local web_dir="${REPO_ROOT}/web"
  local dist_dir="${REPO_ROOT}/src/deckbridge/web_dist"
  if [ ! -f "${web_dir}/package.json" ]; then
    die "web/package.json not found at ${web_dir} — cannot build SPA"
  fi
  log "building frontend (npm ci + npm run build)"
  # Clear any previous build output so files removed by the new source
  # don't linger in the wheel as orphan assets.
  find "${dist_dir}" -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} +
  (
    cd "${web_dir}"
    if [ -f package-lock.json ]; then
      npm ci --silent
    else
      npm install --silent
    fi
    npm run build --silent
  )
  if [ ! -f "${dist_dir}/index.html" ]; then
    die "frontend build did not produce ${dist_dir}/index.html"
  fi
}

create_user() {
  if id "${SERVICE_USER}" >/dev/null 2>&1; then
    log "user ${SERVICE_USER} already exists"
  else
    log "creating system user ${SERVICE_USER}"
    useradd --system --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
  fi
  # plugdev grants HID access via the udev rule.
  if getent group plugdev >/dev/null 2>&1; then
    usermod -aG plugdev "${SERVICE_USER}"
  fi
}

create_dirs() {
  log "creating directories"
  install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0755 "${INSTALL_DIR}"
  install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${DATA_DIR}"
  install -d -o root -g "${SERVICE_USER}" -m 0750 "${CONFIG_DIR}"
}

build_venv() {
  log "creating virtualenv in ${INSTALL_DIR}/venv"
  if [ ! -d "${INSTALL_DIR}/venv" ]; then
    python3 -m venv "${INSTALL_DIR}/venv"
  fi
  "${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip wheel
  log "installing deckbridge from ${REPO_ROOT}"
  "${INSTALL_DIR}/venv/bin/pip" install --quiet "${REPO_ROOT}"
  chown -R "${SERVICE_USER}":"${SERVICE_USER}" "${INSTALL_DIR}"
}

install_udev() {
  log "installing udev rules"
  install -m 0644 "${UDEV_RULE_SRC}" "${UDEV_RULE_DST}"
  udevadm control --reload-rules
  udevadm trigger --subsystem-match=usb --subsystem-match=hidraw || true
}

install_systemd() {
  log "installing systemd unit"
  install -m 0644 "${SYSTEMD_UNIT_SRC}" "${SYSTEMD_UNIT_DST}"
  systemctl daemon-reload
  systemctl enable deckbridge.service
  # Use restart (not `enable --now`) so re-runs of this script — the
  # supported upgrade path — actually pick up the new wheel. enable
  # --now is a no-op when the service is already active, which means
  # backend changes silently failed to take effect on every reinstall
  # before this fix.
  log "restarting deckbridge.service"
  systemctl restart deckbridge.service
}

print_done() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  cat >&2 <<EOF

[deckbridge install] done.

  Service:  systemctl status deckbridge.service
  Logs:     journalctl -u deckbridge -f
  URL:      http://${ip:-<host>}:7878

Open the URL in your browser to run the first-time setup wizard.
EOF
}

main() {
  require_root
  [ -f "${UDEV_RULE_SRC}" ] || die "missing udev rule source: ${UDEV_RULE_SRC}"
  [ -f "${SYSTEMD_UNIT_SRC}" ] || die "missing systemd unit source: ${SYSTEMD_UNIT_SRC}"
  detect_os
  install_apt_deps
  build_frontend
  create_user
  create_dirs
  build_venv
  install_udev
  install_systemd
  print_done
}

main "$@"
