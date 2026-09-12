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
- NetworkManager (`nmcli`)
- `yad` and `libnotify-bin` - rarely present already, so the installer offers to
  install them for you rather than sending you away
- A desktop session; this is a per-user service and runs only while logged in

## Installation

```
git clone https://github.com/fherb2/urbackup-gated.git
cd urbackup-gated
sudo ./install.sh
```

This installs for the user who invoked `sudo`; pass a user name to override it.
If `yad` or `notify-send` is missing, the installer names the package and asks
before installing it; declining stops the installation before anything has been
written. Pass `--yes` to answer that question in advance, for unattended runs.

**The clone is not needed afterwards.** Everything is copied, nothing is linked,
and that includes the uninstaller and this document. You may delete the working
copy once the installation has finished.

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
sudo urbackup-gated-uninstall
```

That command is installed along with the service, so it works whether or not you
still have the working copy; running `sudo ./uninstall.sh` from a clone does the
same thing. The uninstaller re-enables `urbackupclientbackend.service`, since
nothing would be gating it any more, and keeps `/etc/urbackup-gated.conf` -
delete that by hand if you want it gone.

## Where everything lives

| What | Where |
|---|---|
| Configuration | `/etc/urbackup-gated.conf` |
| This document | `/usr/local/share/doc/urbackup-gated/README.md` |
| Commands | `/usr/local/bin/urbackup-gated-ctl`, `urbackup-gated-uninstall` |
| Service and program | `/usr/local/bin/urbackup-gated`, `/usr/local/lib/urbackup-gated/` |
| systemd user unit | `/usr/local/lib/systemd/user/urbackup-gated.service` |
| Privilege grant | `/etc/sudoers.d/urbackup-gated` |
| Network hook | `/etc/NetworkManager/dispatcher.d/90-urbackup-gated` |
| Runtime state | `/run/urbackup-gated/` - gone after every reboot, by design |

The installer records what it put down in
`/usr/local/lib/urbackup-gated/manifest`, and the uninstaller removes exactly
that. Source: <https://github.com/fherb2/urbackup-gated>

## Usage

```
urbackup-gated-ctl status        # what is going on and why
urbackup-gated-ctl deactivate    # stop backing up until further notice
urbackup-gated-ctl activate      # withdraw that
```

Every notification carries a `Details` button that opens the live status window,
and beside it whichever one of those two switches applies right now:
`Deactivate` while backups are allowed, `Activate` once you have turned them
off. That window may be left open; it rewrites itself and suppresses
notifications while it is up.

Logs go to the journal:

```
journalctl --user -u urbackup-gated -f
systemctl --user status urbackup-gated
```

## If the configuration is broken

A missing, unreadable or invalid configuration file keeps the client stopped and
raises an error dialog naming the cause. A missed backup is harmless; an
unchecked backup over a metered connection is the very thing this service
exists to prevent. The service does not restart itself in that state; fix
`/etc/urbackup-gated.conf` and start it again:

```
systemctl --user start urbackup-gated
```

## Privileges

`urbackup-gated` runs unprivileged. It is granted exactly three commands through
`/etc/sudoers.d/urbackup-gated`: `start`, `stop` and `disable` on
`urbackupclientbackend.service`, with no wildcards. `disable` is needed because
the UrBackup client installer re-enables its own service on every run, which
would otherwise bring it up with root privileges before anyone logs in.
