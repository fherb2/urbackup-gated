#!/bin/bash
# Remove urbackup-gated and put the UrBackup client back the way it was.
#
# Usage: sudo urbackup-gated-uninstall
#        sudo ./uninstall.sh          (from a working copy, same thing)
#
# What gets removed is not listed here but read from the manifest that
# install.sh wrote. Carrying the list twice is how a forgotten path ends up
# staying behind forever without anybody noticing.
#
# The configuration file is kept on purpose. Delete /etc/urbackup-gated.conf by
# hand if you want it gone.
set -euo pipefail

LIB_DIR=/usr/local/lib/urbackup-gated
MANIFEST="$LIB_DIR/manifest"
CONFIG_FILE=/etc/urbackup-gated.conf
RUNTIME_DIR=/run/urbackup-gated
CLIENT_UNIT=urbackupclientbackend.service

die() {
    echo "uninstall.sh: $*" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || die "must run as root"

[ -f "$MANIFEST" ] || die "no manifest at $MANIFEST - is urbackup-gated installed?"

# The service user comes from the manifest rather than from SUDO_USER: the
# person removing the software need not be the one it was installed for.
SERVICE_USER=$(sed -n 's/^user //p' "$MANIFEST" | head -1)
[ -n "$SERVICE_USER" ] || die "$MANIFEST names no service user"

echo "Removing urbackup-gated for user $SERVICE_USER"

if id -u "$SERVICE_USER" >/dev/null 2>&1 && [ -d "/run/user/$(id -u "$SERVICE_USER")" ]; then
    SERVICE_UID=$(id -u "$SERVICE_USER")
    sudo -u "$SERVICE_USER" env \
        "XDG_RUNTIME_DIR=/run/user/$SERVICE_UID" \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$SERVICE_UID/bus" \
        systemctl --user disable --now urbackup-gated.service >/dev/null 2>&1 || true
else
    echo "$SERVICE_USER has no active session - stop the service by hand if it still runs"
fi

# Read the whole list before removing anything: the manifest itself lies inside
# one of the entries. Reverse order, so a directory goes after the files inside
# it. This script is an entry too; on Linux that is harmless - the open file
# descriptor keeps working after the name is gone. Verified, do not "fix" it.
removals=$(sed -n 's/^remove //p' "$MANIFEST" | tac)

while IFS= read -r path; do
    [ -n "$path" ] || continue
    rm -rf "$path"
done <<<"$removals"

rm -rf "$RUNTIME_DIR"

# Nothing gates the client any more, so leaving it disabled would silently mean
# no backups at all. Put it back under systemd's own control.
systemctl enable --now "$CLIENT_UNIT" >/dev/null 2>&1 \
    && echo "re-enabled $CLIENT_UNIT" \
    || echo "could not re-enable $CLIENT_UNIT - do it by hand if you still need it"

echo
echo "Done. $CONFIG_FILE was kept."
