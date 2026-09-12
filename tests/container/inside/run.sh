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
USER_UNIT=/usr/local/lib/systemd/user/urbackup-gated.service
MANIFEST=/usr/local/lib/urbackup-gated/manifest
DOC_FILE=/usr/local/share/doc/urbackup-gated/README.md
DISPATCHER=/etc/NetworkManager/dispatcher.d/90-urbackup-gated
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
# A refusal has to leave the system as it was. The sudoers check is the one that
# can fail on a healthy machine, so it is the one worth proving: a stand-in
# visudo that rejects everything, and afterwards not one of our files anywhere.
cat >/usr/local/bin/visudo <<'STUB'
#!/bin/sh
echo "stub visudo: refusing" >&2
exit 1
STUB
chmod 0755 /usr/local/bin/visudo
check_not "install.sh stops when the sudoers file is rejected" \
    "$SOURCE/install.sh" --yes "$SERVICE_USER"
leftovers=
for path in /usr/local/lib/urbackup-gated /usr/local/bin/urbackup-gated \
            /usr/local/bin/urbackup-gated-ctl /usr/local/bin/urbackup-gated-uninstall \
            /usr/local/share/doc/urbackup-gated /etc/sudoers.d/urbackup-gated \
            /etc/tmpfiles.d/urbackup-gated.conf "$DISPATCHER" "$USER_UNIT"; do
    [ -e "$path" ] && leftovers="$leftovers $path"
done
[ -z "$leftovers" ] \
    && ok "a rejected sudoers file leaves no file of ours behind" \
    || no "a rejected sudoers file leaves no file of ours behind -$leftovers"
# The run got as far as offering the runtime packages, so a package may well
# have been installed by then - which is exactly why the message says "no files
# of urbackup-gated" and not "nothing installed". Undo that here, otherwise the
# checks below would find a system that is no longer untouched.
grep -q 'install.*\byad\b' "$TESTDIR/apt-get.log" \
    && ok "the refusal came after the packages, as the message says" \
    || no "the refusal came after the packages, as the message says"
rm -f /usr/local/bin/visudo /usr/local/bin/yad
: >"$TESTDIR/apt-get.log"

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

# The service runs on the system interpreter, so that is the one whose modules
# have to be checked. A virtual environment on PATH would answer instead - and
# its packages are not the ones the service finds. Here that is a python3 in
# /usr/local/bin, which comes first: without the fix the dependency check would
# consult it, fail to import watchdog, install the package, fail again and die.
cat >/usr/local/bin/python3 <<'STUB'
#!/bin/sh
echo "stub python3: this is not the system interpreter" >&2
exit 1
STUB
chmod 0755 /usr/local/bin/python3
check "install.sh ignores a python3 that shadows the system one" \
    "$SOURCE/install.sh" --yes "$SERVICE_USER"
rm -f /usr/local/bin/python3
grep -qx "exec /usr/bin/python3 -u -m urbackup_gated.daemon \"\$@\"" /usr/local/bin/urbackup-gated \
    && ok "the wrapper names the system interpreter" \
    || no "the wrapper names the system interpreter"

check "daemon wrapper is executable" test -x /usr/local/bin/urbackup-gated
check "control tool is executable" test -x /usr/local/bin/urbackup-gated-ctl
check "python package installed" test -f /usr/local/lib/urbackup-gated/urbackup_gated/daemon.py
check "default configuration installed" test -f /etc/urbackup-gated.conf
check "user unit installed" test -f "$USER_UNIT"
check "dispatcher installed" test -x /etc/NetworkManager/dispatcher.d/90-urbackup-gated
check "tmpfiles snippet installed" test -f /etc/tmpfiles.d/urbackup-gated.conf

# The clone is meant to be disposable after the installation, so the way back
# and the documentation have to be in the system, not only in the working copy.
check "uninstaller is installed as a command" test -x /usr/local/bin/urbackup-gated-uninstall
check "documentation is installed" test -f "$DOC_FILE"
check "manifest was written" test -f "$MANIFEST"
grep -qx "user $SERVICE_USER" "$MANIFEST" \
    && ok "manifest names the service user" \
    || no "manifest names the service user"
missing=
for path in /usr/local/lib/urbackup-gated /usr/local/bin/urbackup-gated \
            /usr/local/bin/urbackup-gated-ctl /usr/local/bin/urbackup-gated-uninstall \
            /etc/sudoers.d/urbackup-gated /etc/tmpfiles.d/urbackup-gated.conf \
            "$DISPATCHER" "$USER_UNIT"; do
    grep -qx "remove $path" "$MANIFEST" || missing="$missing $path"
done
[ -z "$missing" ] \
    && ok "manifest records every installed path" \
    || no "manifest records every installed path -$missing"
check_not "the configuration is not in the manifest" \
    grep -q "remove /etc/urbackup-gated.conf" "$MANIFEST"

[ "$(stat -c '%a %U:%G' /etc/sudoers.d/urbackup-gated)" = "440 root:root" ] \
    && ok "sudoers drop-in is 0440 root:root" \
    || no "sudoers drop-in is 0440 root:root"
[ "$(stat -c '%a %U' "$RUNDIR")" = "755 $SERVICE_USER" ] \
    && ok "runtime directory is 0755 and owned by the service user" \
    || no "runtime directory is 0755 and owned by the service user"

check_not "client service was taken out of the system start" \
    systemctl is-enabled --quiet "$CLIENT_UNIT"

# The existence guard is not pedantry: a missing file produces no output that
# the grep would match, so without it the check goes green on nothing at all.
# The exit code of systemd-analyze is unusable here, it is non-zero for harmless
# warnings too - hence the grep.
if [ -f "$USER_UNIT" ] \
    && ! systemd-analyze verify "$USER_UNIT" 2>&1 | grep -qiE 'unknown lvalue|failed to parse'; then
    ok "user unit has no syntax errors"
else
    no "user unit has no syntax errors"
fi

# default.target is reached by any login, an SSH one included. The service is
# meant to live and die with the graphical session, in both directions.
grep -qx "WantedBy=graphical-session.target" "$USER_UNIT" \
    && ok "the unit starts with the graphical session" \
    || no "the unit starts with the graphical session"
grep -qx "PartOf=graphical-session.target" "$USER_UNIT" \
    && ok "the unit ends with the graphical session" \
    || no "the unit ends with the graphical session"
check_not "the unit is not wanted by default.target" \
    grep -q "WantedBy=default.target" "$USER_UNIT"

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
# Without this the whole section is worthless: a missing hook cannot write a
# trigger either, so "no trigger appeared" would read as a pass.
check "dispatcher hook is in place" test -x "$DISPATCHER"
rm -f "$RUNDIR/network-event"
"$DISPATCHER" eth0 up
check "an interface coming up writes the trigger" test -f "$RUNDIR/network-event"
rm -f "$RUNDIR/network-event"
"$DISPATCHER" eth0 dhcp4-change
check "a dhcp change writes the trigger" test -f "$RUNDIR/network-event"
rm -f "$RUNDIR/network-event"
# "Ignored" means it ran through in good order and did nothing - not that it
# crashed before it could do anything, which would leave no trigger either.
check "a vpn coming up leaves the hook succeeding" "$DISPATCHER" wg0 vpn-up
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
daemon_pid=$!

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

# Running it under sudo would leave a root-owned 0600 file that the daemon
# cannot read, which it then reads as "deactivated" and complains about on every
# tick. The file written by the user just above has to stay untouched.
check_not "the control tool refuses to set the flag as root" \
    urbackup-gated-ctl deactivate
[ "$(stat -c %U "$RUNDIR/user-enabled")" = "$SERVICE_USER" ] \
    && ok "the command file still belongs to the service user" \
    || no "the command file still belongs to the service user"

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
if client_active; then
    ok "without any connection the running client is left alone"
else
    no "without any connection the running client is left alone"
    # A dead daemon looks exactly like this and keeps every later check green,
    # so say which of the two it was.
    kill -0 "$daemon_pid" 2>/dev/null \
        && echo "--- the daemon is still running" \
        || echo "--- the daemon is gone"
    echo "--- daemon log"; tail -20 "$TESTDIR/daemon.log"
fi

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

section "shutdown"
pkill -u "$SERVICE_USER" -f urbackup_gated.daemon
check "the client is stopped when the daemon exits" wait_until 15 client_inactive

section "self healing and fail-safe"
# Both were listed under the manual acceptance, although neither needs a display
# or a radio. The scenario is "nothing" at this point, so the network verdict is
# "no decision" and the daemon leaves the client alone - which keeps these two
# checks about what they are meant to be about.

# The UrBackup installer re-enables its own service on every run. Undoing that at
# every start is what the third sudoers entry exists for, and until now no test
# ever walked through that branch: install.sh had already disabled it.
systemctl enable "$CLIENT_UNIT" >/dev/null 2>&1
check "precondition: the client unit is enabled again" \
    systemctl is-enabled --quiet "$CLIENT_UNIT"

: >"$TESTDIR/healing.log"
runuser -u "$SERVICE_USER" -- /usr/local/bin/urbackup-gated \
    >"$TESTDIR/healing.log" 2>&1 &
healing_pid=$!
check "the daemon disables the client unit again at startup" \
    wait_until 20 sh -c '! systemctl is-enabled --quiet '"$CLIENT_UNIT"
grep -q "was enabled at boot" "$TESTDIR/healing.log" \
    && ok "the daemon says so in its log" \
    || no "the daemon says so in its log"
kill "$healing_pid" 2>/dev/null
wait "$healing_pid" 2>/dev/null

# A broken configuration must stop the client and end the daemon in a way that
# systemd can tell from an ordinary failure, so it does not restart into the
# same error dialog every few seconds. Only the dialog itself needs a human.
cp /etc/urbackup-gated.conf "$TESTDIR/config.backup"
echo 'allowed_ssids = [' >/etc/urbackup-gated.conf
systemctl start "$CLIENT_UNIT" >/dev/null 2>&1
check "precondition: the client is running before the fail-safe" client_active

runuser -u "$SERVICE_USER" -- /usr/local/bin/urbackup-gated \
    >"$TESTDIR/failsafe.log" 2>&1
failsafe_code=$?
[ "$failsafe_code" -eq 78 ] \
    && ok "a broken configuration ends the daemon with the agreed exit code" \
    || no "a broken configuration ends the daemon with the agreed exit code (got $failsafe_code)"
check "the fail-safe stops the client" client_inactive
grep -q "configuration error" "$TESTDIR/failsafe.log" \
    && ok "the fail-safe names the cause" \
    || no "the fail-safe names the cause"

cp "$TESTDIR/config.backup" /etc/urbackup-gated.conf

section "removal"
# Absence after the uninstall only says something if the files were there
# beforehand. Asserted here rather than relying on the installation section:
# the entire operating section lies in between.
check "everything to be removed is there beforehand" \
    test -e "$DISPATCHER" -a -e "$USER_UNIT" -a -e /etc/sudoers.d/urbackup-gated \
        -a -e /etc/tmpfiles.d/urbackup-gated.conf -a -e /usr/local/lib/urbackup-gated

# Run the installed copy, not the one in the working copy: that is the way a
# user has after throwing the clone away, and it removes itself in the process.
check "the installed uninstaller succeeds" /usr/local/bin/urbackup-gated-uninstall
check_not "wrapper removed" test -e /usr/local/bin/urbackup-gated
check_not "control tool removed" test -e /usr/local/bin/urbackup-gated-ctl
check_not "uninstaller removed itself" test -e /usr/local/bin/urbackup-gated-uninstall
check_not "package removed" test -e /usr/local/lib/urbackup-gated
check_not "documentation removed" test -e /usr/local/share/doc/urbackup-gated
check_not "sudoers drop-in removed" test -e /etc/sudoers.d/urbackup-gated
check_not "dispatcher removed" test -e "$DISPATCHER"
check_not "tmpfiles snippet removed" test -e /etc/tmpfiles.d/urbackup-gated.conf
check_not "user unit removed" test -e "$USER_UNIT"
check_not "runtime directory removed" test -e "$RUNDIR"
check "configuration deliberately kept" test -f /etc/urbackup-gated.conf
check "client service put back into the system start" \
    systemctl is-enabled --quiet "$CLIENT_UNIT"

printf '\n%s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
