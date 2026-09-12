# urbackup-gated

Desktop notifications for the Linux UrBackup client — and no backups over your phone's data plan.

## Your Linux client backs up in silence

On Windows the UrBackup client sits in the system tray. One glance tells you whether it is connected and whether a backup is running, and you can pause it from there.

On Linux there is none of that. The client is a background service with no desktop presence at all: no icon, no window, no notification. Unless you open a terminal and ask `urbackupclientctl`, you cannot tell whether your laptop has been backing up for the last three weeks or quietly failing. On a machine that travels, that is the real problem — you find out that backups stopped at the moment you need one.

`urbackup-gated` makes the client visible. It notifies you when a backup starts and finishes, when the server connection comes and goes, and every couple of hours while nothing is happening — so silence stops being ambiguous. Every notification carries a **Details** button that opens a live status window; you can leave it open, and it rewrites itself instead of scrolling away.

## No backups over your phone's data plan

UrBackup can recognise a metered connection, but only on Windows — the detection lives in `urbackupclient/win_network_cost.h` and is built for Windows alone. On Linux nothing stops a full backup from pushing tens of gigabytes through a tethered phone with a 2 GB monthly allowance.

So this service also decides whether backing up is allowed at all. You list the Wi-Fi networks you trust; on those and on Ethernet the client runs. On anything else — a hotspot, a café, a network you have never seen — it stays stopped, and starts again by itself once you are back on a network you trust. If the network changes while a backup is running, the backup stops with it.

You can also switch it off by hand for a while, straight from a notification, and the status window tells you it was you and not the network.

## What it looks like

![A notification while a backup runs](images/notification-backup-progress.png)

*A full backup in progress. `Details` opens the status window, `Deactivate` stops backing up until you say otherwise.*

![The status window while a backup runs](images/status-backup-progress.png)

*The status window: which network you are on, whether it is allowed, and how far the backup has got.*

![The status window on a network that is not allowed](images/status-blocked.png)

*The same window on a network that is not on your list — the client has been stopped, and the reason says so.*

## Getting it

You need a systemd desktop with NetworkManager, the UrBackup client, and the system Python 3.11 or newer with `python3-watchdog`. `yad` and `libnotify-bin` are needed too; the installer offers to install them rather than sending you away.

```
git clone https://github.com/fherb2/urbackup-gated.git
cd urbackup-gated
sudo ./install.sh
cd .. && rm -rf urbackup-gated
```

That is the whole installation — everything is copied, nothing is linked, so the clone is expendable afterwards. The service runs per user and only while you are logged in.

**Installation options, usage, configuration and removal are described in [the user documentation](packaging/doc/README.md)**, which is installed along with the service to `/usr/local/share/doc/urbackup-gated/README.md`.

## What is in this repository

| Place | Purpose |
|---|---|
| `src/urbackup_gated/` | The service itself |
| `packaging/` | Everything that is copied to a fixed place in the system, including the user documentation |
| `images/` | Screenshots for this page |
| `tests/` | Unit tests and container integration tests |
| `running_implementation_doc/` | Implementation documentation, roadmap and status — in German |
| `install.sh`, `uninstall.sh` | The entry point |

There is no `pyproject.toml` on purpose: this is a service written in Python, not a library, and nothing here is meant to be importable.

## Tests

```
./tests/run-unit.sh          # no root, no container, no extra packages
./tests/container/run.sh     # needs docker; installs into a throwaway system
```

The container stage installs the service for real, drives it through its trigger files and removes it again — the only way to prove that the installer, the `sudoers` grant and the uninstaller work. A third stage is done by hand, because nobody can check a notification without looking at one.

## License

MIT — see [LICENSE](LICENSE).
