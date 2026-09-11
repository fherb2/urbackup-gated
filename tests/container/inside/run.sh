#!/bin/bash
# Integration tests, executed inside the test container as root.
#
# Covers what unit tests cannot: that install.sh produces a working system,
# that the sudoers grant is narrow, that the trigger files really drive the
# daemon, and that uninstall.sh leaves nothing behind.
set -uo pipefail

SOURCE=/src
TESTDIR=/run/urbackup-gated-test
RUNDIR=/run/urbackup-gated
CLIENT_UNIT=urbackupclientbackend.service
USER_UNIT=/etc/systemd/user/urbackup-gated.service
SERVICE_USER=tester

passed=0
failed=0

ok() { printf 'ok    %s\n' "$1"; passed=$((passed + 1)); }
no() { printf 'FAIL  %s\n' "$1"; failed=$((failed + 1)); }

check() {
    local label=$1
    shift
    if "$@" >/dev/null 2>&1; then ok "$label"; else no "$label"; fi
}

check_not() {
    local label=$1
    shift
    if "$@" >/dev/null 2>&1; then no "$label"; else ok "$label"; fi
}

wait_until() {
    local seconds=$1
    shift
    local waited=0
    while [ "$waited" -lt "$((seconds * 10))" ]; do
        if "$@" >/dev/null 2>&1; then return 0; fi
        sleep 0.1
        waited=$((waited + 1))
    done
    return 1
}

client_active() { systemctl is-active --quiet "$CLIENT_UNIT"; }
client_inactive() { ! systemctl is-active --quiet "$CLIENT_UNIT"; }
as_user() { runuser -u "$SERVICE_USER" -- "$@"; }

section() { printf '\n== %s\n' "$1"; }

# -- prepare the fake surroundings -------------------------------------------

mkdir -p "$TESTDIR"
echo ethernet >"$TESTDIR/scenario"
: >"$TESTDIR/notify-send.log"
: >"$TESTDIR/apt-get.log"
chmod 0777 "$TESTDIR"
chmod 0666 "$TESTDIR/notify-send.log" "$TESTDIR/apt-get.log"

install -m 0644 "$SOURCE/tests/container/stubs/urbackupclientbackend.service" \
    /etc/systemd/system/"$CLIENT_UNIT"
# apt-get is stubbed too: the image deliberately has no yad, so the installer's
# offer to install it is what gets exercised. /usr/local/bin comes before
# /usr/bin, and nothing after the image build needs the real apt-get.
for stub in nmcli urbackupclientctl notify-send apt-get; do
    install -m 0755 "$SOURCE/tests/container/stubs/$stub" /usr/local/bin/"$stub"
done
systemctl daemon-reload

# NetworkManager itself is only faked by the nmcli stub, so the directory it
# would otherwise bring along has to be faked too: install.sh drops its hook in
# there and does not create parent directories.
mkdir -p /etc/NetworkManager/dispatcher.d

# The UrBackup installer enables its service unconditionally; urbackup-gated is
# supposed to undo that.
systemctl enable "$CLIENT_UNIT" >/dev/null 2>&1

section "installation"
check_not "yad is absent to begin with" command -v yad
check "install.sh succeeds" "$SOURCE/install.sh" --yes "$SERVICE_USER"

grep -q 'install.*\byad\b' "$TESTDIR/apt-get.log" \
    && ok "the installer offered and installed the missing yad" \
    || no "the installer offered and installed the missing yad"
check "yad is in place afterwards" command -v yad

# Refusing the package must abort before anything is written. Without --yes and
# without a terminal the read fails, which is the refusal case.
rm -f /usr/local/bin/yad
apt_calls_before=$(wc -l <"$TESTDIR/apt-get.log")
check_not "install.sh stops when the package is refused" \
    "$SOURCE/install.sh" "$SERVICE_USER"
[ "$(wc -l <"$TESTDIR/apt-get.log")" = "$apt_calls_before" ] \
    && ok "a refusal installs nothing" \
    || no "a refusal installs nothing"
# Put the dummy back, so the rest of the run sees a completed installation.
printf '#!/bin/sh\nexit 0\n' >/usr/local/bin/yad
chmod 0755 /usr/local/bin/yad

check "daemon wrapper is executable" test -x /usr/local/bin/urbackup-gated
check "control tool is executable" test -x /usr/local/bin/urbackup-gated-ctl
check "python package installed" test -f /usr/local/lib/urbackup-gated/urbackup_gated/daemon.py
check "default configuration installed" test -f /etc/urbackup-gated.conf
check "user unit installed" test -f "$USER_UNIT"
check "dispatcher installed" test -x /etc/NetworkManager/dispatcher.d/90-urbackup-gated
check "tmpfiles snippet installed" test -f /etc/tmpfiles.d/urbackup-gated.conf

[ "$(stat -c '%a %U:%G' /etc/sudoers.d/urbackup-gated)" = "440 root:root" ] \
    && ok "sudoers drop-in is 0440 root:root" \
    || no "sudoers drop-in is 0440 root:root"
[ "$(stat -c '%a %U' "$RUNDIR")" = "755 $SERVICE_USER" ] \
    && ok "runtime directory is 0755 and owned by the service user" \
    || no "runtime directory is 0755 and owned by the service user"

check_not "client service was taken out of the system start" \
    systemctl is-enabled --quiet "$CLIENT_UNIT"

if ! systemd-analyze verify "$USER_UNIT" 2>&1 | grep -qiE 'unknown lvalue|failed to parse'; then
    ok "user unit has no syntax errors"
else
    no "user unit has no syntax errors"
fi

section "privileges are narrow"
systemctl stop "$CLIENT_UNIT" >/dev/null 2>&1
check "granted: start the client unit" \
    as_user sudo -n /usr/bin/systemctl start "$CLIENT_UNIT"
check "granted: stop the client unit" \
    as_user sudo -n /usr/bin/systemctl stop "$CLIENT_UNIT"
check "granted: disable the client unit" \
    as_user sudo -n /usr/bin/systemctl disable "$CLIENT_UNIT"
check_not "refused: restart the client unit" \
    as_user sudo -n /usr/bin/systemctl restart "$CLIENT_UNIT"
check_not "refused: touch a different unit" \
    as_user sudo -n /usr/bin/systemctl start dbus.service
check_not "refused: a shell" as_user sudo -n /bin/sh -c true
check_not "refused: systemctl without the unit argument" \
    as_user sudo -n /usr/bin/systemctl start

section "dispatcher event filter"
rm -f "$RUNDIR/network-event"
/etc/NetworkManager/dispatcher.d/90-urbackup-gated eth0 up
check "an interface coming up writes the trigger" test -f "$RUNDIR/network-event"
rm -f "$RUNDIR/network-event"
/etc/NetworkManager/dispatcher.d/90-urbackup-gated eth0 dhcp4-change
check "a dhcp change writes the trigger" test -f "$RUNDIR/network-event"
rm -f "$RUNDIR/network-event"
/etc/NetworkManager/dispatcher.d/90-urbackup-gated wg0 vpn-up
check_not "a vpn coming up is ignored" test -f "$RUNDIR/network-event"

section "the daemon in operation"
# A long check interval on purpose: everything that reacts faster than this
# proves the event path works rather than the fallback timer.
cat >/etc/urbackup-gated.conf <<'CONF'
allowed_ssids = ["allowed-net"]

[intervals]
check_seconds = 60
check_seconds_window_open = 5
idle_notify_seconds = 86400
progress_notify_seconds = 86400

[notify]
timeout_seconds = 1
CONF

echo ethernet >"$TESTDIR/scenario"
systemctl stop "$CLIENT_UNIT" >/dev/null 2>&1
runuser -u "$SERVICE_USER" -- /usr/local/bin/urbackup-gated \
    >"$TESTDIR/daemon.log" 2>&1 &

if wait_until 20 test -f "$RUNDIR/state.json"; then
    ok "daemon writes the status file"
else
    no "daemon writes the status file"
    echo "--- daemon log"; cat "$TESTDIR/daemon.log"
fi

if wait_until 20 client_active; then
    ok "ethernet lets the client start"
else
    no "ethernet lets the client start"
    echo "--- daemon log"; cat "$TESTDIR/daemon.log"
fi

# The daemon writes state.json into the directory it watches. If its own writes
# woke it up, this would spin instead of resting until the 60 second tick.
before=$(stat -c %y "$RUNDIR/state.json")
sleep 8
after=$(stat -c %y "$RUNDIR/state.json")
[ "$before" = "$after" ] \
    && ok "own status writes do not wake the loop" \
    || no "own status writes do not wake the loop"

echo forbidden_wifi >"$TESTDIR/scenario"
touch "$RUNDIR/network-event"
check "a forbidden wifi stops the client" wait_until 10 client_inactive

echo allowed_wifi >"$TESTDIR/scenario"
touch "$RUNDIR/network-event"
check "an allowed wifi starts it again" wait_until 10 client_active

check "the control tool accepts deactivate" as_user urbackup-gated-ctl deactivate
check "manual deactivation stops the client" wait_until 10 client_inactive

check "status tool succeeds" as_user urbackup-gated-ctl status
as_user urbackup-gated-ctl status >"$TESTDIR/status.txt" 2>&1
grep -q "manually deactivated" "$TESTDIR/status.txt" \
    && ok "status names the manual deactivation as the reason" \
    || no "status names the manual deactivation as the reason"

as_user urbackup-gated-ctl activate >/dev/null 2>&1
check "activation lets it run again" wait_until 10 client_active

echo nothing >"$TESTDIR/scenario"
touch "$RUNDIR/network-event"
sleep 2
check "without any connection the running client is left alone" client_active

python3 - "$RUNDIR/state.json" <<'PY' && ok "status file matches the agreed schema" || no "status file matches the agreed schema"
import json, sys
d = json.load(open(sys.argv[1]))
assert d["schema_version"] == 1, d.get("schema_version")
assert set(d) >= {"written_at", "network", "decision", "urbackup_client"}
assert set(d["decision"]) == {"network_allows", "user_enabled", "effective", "reason"}
PY

grep -q 'details=Details' "$TESTDIR/notify-send.log" \
    && ok "notifications offer the details button" \
    || no "notifications offer the details button"
grep -qE 'deactivate=Deactivate|activate=Activate' "$TESTDIR/notify-send.log" \
    && ok "notifications offer the manual switch" \
    || no "notifications offer the manual switch"

section "shutdown and removal"
pkill -u "$SERVICE_USER" -f urbackup_gated.daemon
check "the client is stopped when the daemon exits" wait_until 15 client_inactive

check "uninstall.sh succeeds" "$SOURCE/uninstall.sh" "$SERVICE_USER"
check_not "wrapper removed" test -e /usr/local/bin/urbackup-gated
check_not "control tool removed" test -e /usr/local/bin/urbackup-gated-ctl
check_not "package removed" test -e /usr/local/lib/urbackup-gated
check_not "sudoers drop-in removed" test -e /etc/sudoers.d/urbackup-gated
check_not "dispatcher removed" test -e /etc/NetworkManager/dispatcher.d/90-urbackup-gated
check_not "tmpfiles snippet removed" test -e /etc/tmpfiles.d/urbackup-gated.conf
check_not "user unit removed" test -e "$USER_UNIT"
check_not "runtime directory removed" test -e "$RUNDIR"
check "configuration deliberately kept" test -f /etc/urbackup-gated.conf
check "client service put back into the system start" \
    systemctl is-enabled --quiet "$CLIENT_UNIT"

printf '\n%s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
