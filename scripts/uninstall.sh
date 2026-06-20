#!/usr/bin/env bash
# DeckBridge bare-metal uninstaller.
#
# Removes the systemd unit, virtualenv, and udev rules. By default leaves
# the user's stored configuration (decks, pages, keys, settings) and data
# in place. Pass --purge to also wipe /var/lib/deckbridge and
# /etc/deckbridge and remove the service user.
#
# Usage:
#   sudo ./scripts/uninstall.sh           # keep user data
#   sudo ./scripts/uninstall.sh --purge   # wipe everything

set -euo pipefail

INSTALL_DIR=${DECKBRIDGE_INSTALL_DIR:-/opt/deckbridge}
DATA_DIR=${DECKBRIDGE_DATA_DIR:-/var/lib/deckbridge}
CONFIG_DIR=${DECKBRIDGE_CONFIG_DIR:-/etc/deckbridge}
SERVICE_USER=${DECKBRIDGE_SERVICE_USER:-deckbridge}
UDEV_RULE_DST="/etc/udev/rules.d/99-streamdeck.rules"
SYSTEMD_UNIT_DST="/etc/systemd/system/deckbridge.service"

PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    -h|--help)
      sed -n '2,12p' "$0" >&2
      exit 0
      ;;
    *) printf 'unknown arg: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

log() { printf '[deckbridge uninstall] %s\n' "$*" >&2; }

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    printf '[deckbridge uninstall] ERROR: must run as root (try: sudo %s)\n' "$0" >&2
    exit 1
  fi
}

stop_service() {
  if systemctl list-unit-files deckbridge.service >/dev/null 2>&1; then
    log "stopping & disabling deckbridge.service"
    systemctl disable --now deckbridge.service || true
  fi
  if [ -f "${SYSTEMD_UNIT_DST}" ]; then
    log "removing ${SYSTEMD_UNIT_DST}"
    rm -f "${SYSTEMD_UNIT_DST}"
    systemctl daemon-reload
  fi
}

remove_udev() {
  if [ -f "${UDEV_RULE_DST}" ]; then
    log "removing ${UDEV_RULE_DST}"
    rm -f "${UDEV_RULE_DST}"
    udevadm control --reload-rules || true
  fi
}

remove_install() {
  if [ -d "${INSTALL_DIR}" ]; then
    log "removing ${INSTALL_DIR}"
    rm -rf "${INSTALL_DIR}"
  fi
}

purge_data() {
  if [ "${PURGE}" -ne 1 ]; then
    log "keeping user data in ${DATA_DIR} and ${CONFIG_DIR}"
    log "(re-run with --purge to delete them)"
    return
  fi
  if [ -d "${DATA_DIR}" ]; then
    log "purging ${DATA_DIR}"
    rm -rf "${DATA_DIR}"
  fi
  if [ -d "${CONFIG_DIR}" ]; then
    log "purging ${CONFIG_DIR}"
    rm -rf "${CONFIG_DIR}"
  fi
  if id "${SERVICE_USER}" >/dev/null 2>&1; then
    log "removing user ${SERVICE_USER}"
    userdel "${SERVICE_USER}" || true
  fi
}

main() {
  require_root
  stop_service
  remove_udev
  remove_install
  purge_data
  log "done."
}

main "$@"
