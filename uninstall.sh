#!/bin/bash
# Remove urbackup-gated and put the UrBackup client back the way it was.
#
# Usage: sudo ./uninstall.sh [user]
#
# The configuration file is kept on purpose. Delete /etc/urbackup-gated.conf by
# hand if you want it gone.
set -euo pipefail

LIB_DIR=/usr/local/lib/urbackup-gated
BIN_DIR=/usr/local/bin
CONFIG_FILE=/etc/urbackup-gated.conf
UNIT_FILE=/etc/systemd/user/urbackup-gated.service
DISPATCHER_FILE=/etc/NetworkManager/dispatcher.d/90-urbackup-gated
TMPFILES_FILE=/etc/tmpfiles.d/urbackup-gated.conf
SUDOERS_FILE=/etc/sudoers.d/urbackup-gated
RUNTIME_DIR=/run/urbackup-gated
CLIENT_UNIT=urbackupclientbackend.service

die() {
    echo "uninstall.sh: $*" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || die "must run as root"

SERVICE_USER=${1:-${SUDO_USER:-}}
[ -n "$SERVICE_USER" ] || die "cannot tell which user to uninstall for - pass it as an argument"
id -u "$SERVICE_USER" >/dev/null 2>&1 || die "no such user: $SERVICE_USER"
SERVICE_UID=$(id -u "$SERVICE_USER")

echo "Removing urbackup-gated for user $SERVICE_USER"

if [ -d "/run/user/$SERVICE_UID" ]; then
    sudo -u "$SERVICE_USER" env \
        "XDG_RUNTIME_DIR=/run/user/$SERVICE_UID" \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$SERVICE_UID/bus" \
        systemctl --user disable --now urbackup-gated.service >/dev/null 2>&1 || true
else
    echo "$SERVICE_USER has no active session - stop the service by hand if it still runs"
fi

rm -f "$UNIT_FILE" "$DISPATCHER_FILE" "$TMPFILES_FILE" "$SUDOERS_FILE"
rm -f "$BIN_DIR/urbackup-gated" "$BIN_DIR/urbackup-gated-ctl"
rm -rf "$LIB_DIR"
rm -rf "$RUNTIME_DIR"

# Nothing gates the client any more, so leaving it disabled would silently mean
# no backups at all. Put it back under systemd's own control.
systemctl enable --now "$CLIENT_UNIT" >/dev/null 2>&1 \
    && echo "re-enabled $CLIENT_UNIT" \
    || echo "could not re-enable $CLIENT_UNIT - do it by hand if you still need it"

echo
echo "Done. $CONFIG_FILE was kept."
