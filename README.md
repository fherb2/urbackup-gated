# urbackup-gated

Keeps the UrBackup client from backing up over a metered connection on Linux.

UrBackup can detect metered connections, but only on Windows. On Linux there is
nothing stopping the client from pushing a full backup through a phone hotspot
with a 2 GB monthly allowance. `urbackup-gated` closes that gap: it decides
whether `urbackupclientbackend.service` is allowed to run, based on the networks
currently connected, and starts or stops it accordingly.

It also provides the desktop status reporting that the Linux client lacks:
notifications when something changes, and a status window that rewrites itself
while it stays open.

## How it decides

All active physical connections are judged, not just the primary one:

- Any active wifi connection whose SSID is **not** on the allow list forbids
  backups. This applies even when ethernet is connected at the same time.
- Otherwise, if at least one connection is active, backups are allowed.
- With no active connection at all, nothing is changed: a running backup keeps
  running, a stopped client stays stopped.

That verdict is combined with a manual flag you control, and backups run only
when both agree. The manual flag can never override the network rule - it only
withdraws or restores your own objection.

The strictness is deliberate. Which interface traffic actually takes is not
reliably predictable from the outside, so a forbidden network anywhere means
stop. The price: with ethernet and a foreign wifi connected at once, no backup
runs even though it would be safe. Switch the wifi off in that case.

## Requirements

- The UrBackup client, providing `urbackupclientbackend.service`
- Python 3.11 or newer, and `python3-watchdog`
- `yad`, `libnotify-bin`, NetworkManager (`nmcli`)
- A desktop session; this is a per-user service and runs only while logged in

## Installation

```
sudo ./install.sh
```

This installs for the user who invoked `sudo`; pass a user name to override it.
Then review the allow list in `/etc/urbackup-gated.conf`, which is the one
setting you have to get right:

```toml
allowed_ssids = ["home-wifi", "office-wifi"]
```

SSIDs are compared case sensitively. After editing, restart the service:

```
systemctl --user restart urbackup-gated
```

To remove everything again:

```
sudo ./uninstall.sh
```

The uninstaller re-enables `urbackupclientbackend.service`, since nothing would
be gating it any more.

## Usage

```
urbackup-gated-ctl status        # what is going on and why
urbackup-gated-ctl deactivate    # stop backing up until further notice
urbackup-gated-ctl activate      # withdraw that
```

The same two commands are available as buttons on every notification, next to a
`Details` button that opens the live status window. That window may be left
open; it rewrites itself and suppresses notifications while it is up.

Logs go to the journal:

```
journalctl --user -u urbackup-gated -f
systemctl --user status urbackup-gated
```

## If the configuration is broken

A missing, unreadable or invalid configuration file keeps the client stopped and
raises an error dialog naming the cause. A missed backup is harmless; an
unchecked backup over a metered connection is the very thing this service
exists to prevent. The service does not restart itself in that state - fix the
file and start it again.

## Privileges

`urbackup-gated` runs unprivileged. It is granted exactly three commands through
`/etc/sudoers.d/urbackup-gated`: `start`, `stop` and `disable` on
`urbackupclientbackend.service`, with no wildcards. `disable` is needed because
the UrBackup client installer re-enables its own service on every run, which
would otherwise bring it up with root privileges before anyone logs in.
