#!/bin/bash
# Install urbackup-gated for one user.
#
# Usage: sudo ./install.sh [--yes] [user]
#
# The user defaults to the one who invoked sudo. urbackup-gated is a per-user
# service: it runs in that user's session, and only that user may steer it.
#
# --yes answers the question about missing runtime packages with yes, for
# unattended runs such as the container tests.
set -euo pipefail

LIB_DIR=/usr/local/lib/urbackup-gated
BIN_DIR=/usr/local/bin
DOC_DIR=/usr/local/share/doc/urbackup-gated
CONFIG_FILE=/etc/urbackup-gated.conf
# Not /etc/systemd/user: that is the administrator's place for overrides, while
# this is shipped along with the software, which lives under /usr/local.
UNIT_DIR=/usr/local/lib/systemd/user
UNIT_FILE="$UNIT_DIR/urbackup-gated.service"
DISPATCHER_FILE=/etc/NetworkManager/dispatcher.d/90-urbackup-gated
TMPFILES_FILE=/etc/tmpfiles.d/urbackup-gated.conf
SUDOERS_FILE=/etc/sudoers.d/urbackup-gated
MANIFEST="$LIB_DIR/manifest"
CLIENT_UNIT=urbackupclientbackend.service

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

die() {
    echo "install.sh: $*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required but not installed${2:+ ($2)}"
}

# What is asked for here is not a privilege - the installer already runs as root
# - but the user's consent to put another package on their machine. The package
# manager is called through PATH on purpose, so the container tests can put a
# recording stand-in in front of it instead of really pulling GTK in.
ensure_package() {
    local program=$1 package=$2 answer=
    command -v "$program" >/dev/null 2>&1 && return 0

    echo
    echo "$program is missing. urbackup-gated needs it; it comes with the package '$package'."
    if [ "$ASSUME_YES" -ne 1 ]; then
        printf 'Install %s now? [y/N] ' "$package"
        # Braces so the shell's own complaint about a missing /dev/tty - the
        # unattended case - is swallowed along with read's.
        { read -r answer </dev/tty; } 2>/dev/null || answer=
        case $answer in
            [yY] | [yY][eE][sS]) ;;
            *) die "$package is required - install it yourself and run install.sh again" ;;
        esac
    fi

    echo "installing $package"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$package" \
        || die "could not install $package - install it yourself and run install.sh again"
    command -v "$program" >/dev/null 2>&1 \
        || die "$package was installed but $program is still not there"
}

[ "$(id -u)" -eq 0 ] || die "must run as root"

ASSUME_YES=0
while [ $# -gt 0 ]; do
    case $1 in
        --yes) ASSUME_YES=1; shift ;;
        --) shift; break ;;
        -*) die "unknown option: $1" ;;
        *) break ;;
    esac
done

SERVICE_USER=${1:-${SUDO_USER:-}}
[ -n "$SERVICE_USER" ] || die "cannot tell which user to install for - pass it as an argument"
[ "$SERVICE_USER" != root ] || die "refusing to install for root - this is a desktop session service"
id -u "$SERVICE_USER" >/dev/null 2>&1 || die "no such user: $SERVICE_USER"

SERVICE_UID=$(id -u "$SERVICE_USER")
SERVICE_GROUP=$(id -gn "$SERVICE_USER")

echo "Installing urbackup-gated for user $SERVICE_USER"

# -- dependencies ------------------------------------------------------------

need python3
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

# These two are rarely present on a desktop already, so they are offered rather
# than demanded. Nothing has been written to the system at this point, so a
# refusal leaves no half-installed state behind.
ensure_package yad yad
ensure_package notify-send libnotify-bin

# -- privileges, checked before anything is written ---------------------------
# A broken sudoers file locks sudo out system wide, so it is written to a
# temporary file and validated first. That validation happens here, ahead of the
# first file we put down, so its refusal really does leave the system untouched
# - the file itself is installed further below, in its own section.

sudoers_tmp=$(mktemp)
trap 'rm -f "$sudoers_tmp"' EXIT
sed -e "s/@USER@/$SERVICE_USER/" \
    "$SOURCE_DIR/packaging/sudoers.d/urbackup-gated" >"$sudoers_tmp"
# Not "nothing installed": a runtime package may have been added just above.
# What is true is that none of our own files exist yet.
visudo -c -q -f "$sudoers_tmp" \
    || die "the generated sudoers file is invalid - no files of urbackup-gated were written"

# -- manifest ----------------------------------------------------------------
# Everything this script puts down is recorded here, and uninstall.sh works from
# that record alone. Without it both scripts would carry the same list of paths,
# and a path added to only one of them would silently leave a file behind.
#
# Deliberately absent from the record: the configuration file. It is meant to
# survive the uninstall, so it is nothing to be removed.

record() {
    printf 'remove %s\n' "$1" >>"$MANIFEST"
}

# -- python package ----------------------------------------------------------

rm -rf "$LIB_DIR/urbackup_gated"
install -d -m 0755 "$LIB_DIR"

: >"$MANIFEST"
chmod 0644 "$MANIFEST"
printf 'user %s\n' "$SERVICE_USER" >>"$MANIFEST"
record "$LIB_DIR"
cp -r "$SOURCE_DIR/src/urbackup_gated" "$LIB_DIR/"
find "$LIB_DIR/urbackup_gated" -type d -exec chmod 0755 {} +
find "$LIB_DIR/urbackup_gated" -type f -exec chmod 0644 {} +
rm -rf "$LIB_DIR/urbackup_gated/__pycache__"

write_wrapper() {
    local path=$1 module=$2
    # -u is not a detail: without it Python buffers stdout in blocks as soon as
    # it is not a terminal, which under systemd it never is. The journal would
    # then stay empty until the buffer fills or the service ends - for a daemon
    # that runs for days and whose only diagnostic channel is the journal, that
    # is an outage of the logging.
    cat >"$path" <<EOF
#!/bin/sh
PYTHONPATH=$LIB_DIR
export PYTHONPATH
exec /usr/bin/python3 -u -m $module "\$@"
EOF
    chmod 0755 "$path"
}

write_wrapper "$BIN_DIR/urbackup-gated" urbackup_gated.daemon
write_wrapper "$BIN_DIR/urbackup-gated-ctl" urbackup_gated.cli
record "$BIN_DIR/urbackup-gated"
record "$BIN_DIR/urbackup-gated-ctl"

# -- uninstaller and documentation -------------------------------------------
# Both used to live in the clone only. Since everything else is copied, throwing
# the clone away afterwards is the obvious thing to do - and left the user with
# no way back and no documentation.

install -m 0755 -o root -g root \
    "$SOURCE_DIR/uninstall.sh" "$BIN_DIR/urbackup-gated-uninstall"
record "$BIN_DIR/urbackup-gated-uninstall"

install -d -m 0755 "$DOC_DIR"
install -m 0644 -o root -g root "$SOURCE_DIR/README.md" "$DOC_DIR/README.md"
record "$DOC_DIR"

# -- runtime directory -------------------------------------------------------

sed -e "s/@USER@/$SERVICE_USER/" -e "s/@GROUP@/$SERVICE_GROUP/" \
    "$SOURCE_DIR/packaging/tmpfiles.d/urbackup-gated.conf" >"$TMPFILES_FILE"
chmod 0644 "$TMPFILES_FILE"
systemd-tmpfiles --create "$TMPFILES_FILE"
record "$TMPFILES_FILE"

# -- privileges --------------------------------------------------------------
# Generated and validated further up, before the first file was written.

install -m 0440 -o root -g root "$sudoers_tmp" "$SUDOERS_FILE"
record "$SUDOERS_FILE"

# -- network events ----------------------------------------------------------

install -m 0755 -o root -g root \
    "$SOURCE_DIR/packaging/networkmanager/90-urbackup-gated" "$DISPATCHER_FILE"
record "$DISPATCHER_FILE"

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
record "$UNIT_FILE"

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
    run_as_user systemctl --user enable urbackup-gated.service
    # restart, not "enable --now": that starts only what is not already running,
    # so an installation over an existing one left the old code running until
    # the next logout while the new one sat on disk. restart also starts a unit
    # that is not running, which makes a case distinction unnecessary.
    run_as_user systemctl --user restart urbackup-gated.service
    echo
    echo "urbackup-gated is enabled and running."
    echo "Status:  urbackup-gated-ctl status"
    echo "Log:     journalctl --user -u urbackup-gated -f"
else
    echo
    echo "$SERVICE_USER has no active session, so the service was not started."
    echo "Run this as $SERVICE_USER from the graphical session:"
    echo "  systemctl --user daemon-reload"
    echo "  systemctl --user enable urbackup-gated.service"
    echo "  systemctl --user restart urbackup-gated.service"
fi
