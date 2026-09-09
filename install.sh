#!/bin/bash
# Install urbackup-gated for one user.
#
# Usage: sudo ./install.sh [user]
#
# The user defaults to the one who invoked sudo. urbackup-gated is a per-user
# service: it runs in that user's session, and only that user may steer it.
set -euo pipefail

LIB_DIR=/usr/local/lib/urbackup-gated
BIN_DIR=/usr/local/bin
CONFIG_FILE=/etc/urbackup-gated.conf
UNIT_DIR=/etc/systemd/user
UNIT_FILE="$UNIT_DIR/urbackup-gated.service"
DISPATCHER_FILE=/etc/NetworkManager/dispatcher.d/90-urbackup-gated
TMPFILES_FILE=/etc/tmpfiles.d/urbackup-gated.conf
SUDOERS_FILE=/etc/sudoers.d/urbackup-gated
CLIENT_UNIT=urbackupclientbackend.service

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

die() {
    echo "install.sh: $*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required but not installed${2:+ ($2)}"
}

[ "$(id -u)" -eq 0 ] || die "must run as root"

SERVICE_USER=${1:-${SUDO_USER:-}}
[ -n "$SERVICE_USER" ] || die "cannot tell which user to install for - pass it as an argument"
[ "$SERVICE_USER" != root ] || die "refusing to install for root - this is a desktop session service"
id -u "$SERVICE_USER" >/dev/null 2>&1 || die "no such user: $SERVICE_USER"

SERVICE_UID=$(id -u "$SERVICE_USER")
SERVICE_GROUP=$(id -gn "$SERVICE_USER")

echo "Installing urbackup-gated for user $SERVICE_USER"

# -- dependencies ------------------------------------------------------------

need python3
need yad "apt install yad"
need notify-send "apt install libnotify-bin"
need nmcli "part of network-manager"
need systemd-tmpfiles
need visudo
need systemctl

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "python3 3.11 or newer is required (tomllib)"
python3 -c 'import watchdog' 2>/dev/null \
    || die "the watchdog module is required (apt install python3-watchdog)"

systemctl cat "$CLIENT_UNIT" >/dev/null 2>&1 \
    || die "$CLIENT_UNIT not found - install the UrBackup client first"

# -- python package ----------------------------------------------------------

rm -rf "$LIB_DIR/urbackup_gated"
install -d -m 0755 "$LIB_DIR"
cp -r "$SOURCE_DIR/src/urbackup_gated" "$LIB_DIR/"
find "$LIB_DIR/urbackup_gated" -type d -exec chmod 0755 {} +
find "$LIB_DIR/urbackup_gated" -type f -exec chmod 0644 {} +
rm -rf "$LIB_DIR/urbackup_gated/__pycache__"

write_wrapper() {
    local path=$1 module=$2
    cat >"$path" <<EOF
#!/bin/sh
PYTHONPATH=$LIB_DIR
export PYTHONPATH
exec /usr/bin/python3 -m $module "\$@"
EOF
    chmod 0755 "$path"
}

write_wrapper "$BIN_DIR/urbackup-gated" urbackup_gated.daemon
write_wrapper "$BIN_DIR/urbackup-gated-ctl" urbackup_gated.cli

# -- runtime directory -------------------------------------------------------

sed -e "s/@USER@/$SERVICE_USER/" -e "s/@GROUP@/$SERVICE_GROUP/" \
    "$SOURCE_DIR/packaging/tmpfiles.d/urbackup-gated.conf" >"$TMPFILES_FILE"
chmod 0644 "$TMPFILES_FILE"
systemd-tmpfiles --create "$TMPFILES_FILE"

# -- privileges --------------------------------------------------------------
# Written to a temporary file and checked first: a broken sudoers file locks
# sudo out system wide.

sudoers_tmp=$(mktemp)
trap 'rm -f "$sudoers_tmp"' EXIT
sed -e "s/@USER@/$SERVICE_USER/" \
    "$SOURCE_DIR/packaging/sudoers.d/urbackup-gated" >"$sudoers_tmp"
visudo -c -q -f "$sudoers_tmp" || die "generated sudoers file is invalid - nothing installed"
install -m 0440 -o root -g root "$sudoers_tmp" "$SUDOERS_FILE"

# -- network events ----------------------------------------------------------

install -m 0755 -o root -g root \
    "$SOURCE_DIR/packaging/networkmanager/90-urbackup-gated" "$DISPATCHER_FILE"

# -- configuration -----------------------------------------------------------

if [ -e "$CONFIG_FILE" ]; then
    echo "keeping existing $CONFIG_FILE"
else
    install -m 0644 -o root -g root \
        "$SOURCE_DIR/packaging/config/urbackup-gated.conf" "$CONFIG_FILE"
    echo "installed default $CONFIG_FILE - review the allowed SSIDs"
fi

# -- the units ---------------------------------------------------------------

install -d -m 0755 "$UNIT_DIR"
install -m 0644 -o root -g root \
    "$SOURCE_DIR/packaging/systemd/urbackup-gated.service" "$UNIT_FILE"

# The UrBackup client must not come up with root privileges before anyone logs
# in; urbackup-gated is from now on the only thing that starts it.
systemctl disable --now "$CLIENT_UNIT" >/dev/null 2>&1 || true

if [ -d "/run/user/$SERVICE_UID" ]; then
    run_as_user() {
        sudo -u "$SERVICE_USER" env \
            "XDG_RUNTIME_DIR=/run/user/$SERVICE_UID" \
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$SERVICE_UID/bus" \
            "$@"
    }
    run_as_user systemctl --user daemon-reload
    run_as_user systemctl --user enable --now urbackup-gated.service
    echo
    echo "urbackup-gated is enabled and running."
    echo "Status:  urbackup-gated-ctl status"
    echo "Log:     journalctl --user -u urbackup-gated -f"
else
    echo
    echo "$SERVICE_USER has no active session, so the service was not started."
    echo "Run this as $SERVICE_USER after the next login:"
    echo "  systemctl --user daemon-reload"
    echo "  systemctl --user enable --now urbackup-gated.service"
fi
