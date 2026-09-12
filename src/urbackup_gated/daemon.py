"""The gating daemon: decide, act, report."""

import os
import queue
import signal
import sys
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import client, runtime, state, ui
from .config import Config, ConfigError, load

# sysexits.h EX_CONFIG. The unit file refuses to restart on this code, so a
# broken configuration does not loop error windows every few seconds.
EX_CONFIG = 78


class _TriggerHandler(FileSystemEventHandler):
    """Wakes the main loop when one of the two trigger files changes."""

    def __init__(self, wake: threading.Event) -> None:
        self._wake = wake

    def on_any_event(self, event) -> None:
        paths = (event.src_path, getattr(event, "dest_path", "") or "")
        if any(os.path.basename(path) in runtime.WATCHED_NAMES for path in paths):
            self._wake.set()


def _known_change(previous: bool | None, current: bool | None) -> bool:
    """True only for a transition between two known values.

    An unreachable backend leaves the client flags unknown rather than false,
    and unknown is neither of the two states the notification rules name.
    Without this guard every gated stop is followed one tick later by a message
    about a lost server connection that never happened.
    """
    return previous is not None and current is not None and previous != current


class Daemon:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._requests: queue.Queue[str] = queue.Queue()
        self._window: ui.StatusWindow | None = None
        self._notify_in_flight = False
        self._previous_client: dict | None = None
        self._last_idle_notify = 0.0
        self._last_progress_notify = 0.0

    # -- lifecycle ---------------------------------------------------------

    def run(self) -> int:
        runtime.check_directory()
        if not ui.yad_available():
            print(
                "yad is not installed - neither the status window nor error "
                "dialogs will appear",
                file=sys.stderr,
            )

        self._enforce_disabled()
        runtime.clear_user_enabled()

        observer = Observer()
        observer.schedule(_TriggerHandler(self._wake), str(runtime.RUNTIME_DIR))
        observer.start()

        now = time.monotonic()
        self._last_idle_notify = now
        self._last_progress_notify = now

        try:
            self._loop()
        finally:
            observer.stop()
            observer.join(timeout=5)
            self._close_window()
            self._stop_client_on_exit()
        return 0

    def request_stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._drain_requests()

            status = state.gather(self._config)
            action = self._apply(status)
            if action is not None:
                status["urbackup_client"]["unit_active"] = action == "started"
            runtime.write_state(status)

            self._refresh_window(status)
            self._report(status, action)

            interval = (
                self._config.check_seconds_window_open
                if self._window is not None
                else self._config.check_seconds
            )
            self._wake.wait(interval)
            self._wake.clear()

    def _enforce_disabled(self) -> None:
        """Undo the unconditional systemctl enable of the UrBackup installer."""
        try:
            # Unknown counts as enabled: attempting the disable is cheap and
            # says so if it fails, while skipping it would leave the client to
            # come up with root privileges before anyone logs in.
            if client.is_enabled() is not False:
                client.disable()
                print(f"{client.UNIT} was enabled at boot - disabled it")
        except client.ControlError as error:
            print(f"cannot disable {client.UNIT}: {error}", file=sys.stderr)

    def _stop_client_on_exit(self) -> None:
        """Backups must not outlive the session this daemon belongs to."""
        try:
            if client.is_active() is not False:
                client.stop()
                print(f"stopped {client.UNIT} on shutdown")
        except client.ControlError as error:
            print(f"cannot stop {client.UNIT} on shutdown: {error}", file=sys.stderr)

    # -- decision ----------------------------------------------------------

    def _apply(self, status: dict) -> str | None:
        effective = status["decision"]["effective"]
        if effective is None:
            return None
        # An unanswerable unit state counts as "running". That is the only
        # direction that stays safe in both branches: over a forbidden network a
        # stop is at least attempted, and over an allowed one a start is merely
        # postponed. The opposite assumption would leave a running client on a
        # metered link with nobody stopping it.
        active = status["urbackup_client"]["unit_active"] is not False
        try:
            if effective and not active:
                client.start()
                return "started"
            if not effective and active:
                client.stop()
                return "stopped"
        except client.ControlError as error:
            print(error, file=sys.stderr)
        return None

    # -- reporting ---------------------------------------------------------

    def _report(self, status: dict, action: str | None) -> None:
        client_view = status["urbackup_client"]
        previous = self._previous_client

        # While the status window is open the notifications would only repeat
        # what is already on screen. The previous state moves on regardless:
        # here the suppression is intended, and holding the changes back would
        # produce a burst of stale messages the moment the window closes.
        if self._window is not None:
            self._previous_client = client_view
            return

        # Everywhere else the previous state only moves on once the change has
        # actually been reported. A notification that was held back because
        # another one still hangs on screen is retried on the next tick instead
        # of being lost for good.
        if action is not None:
            reason = status["decision"]["reason"]
            if self._notify(f"UrBackup client {action}", reason, status):
                self._previous_client = client_view
            return

        if previous is not None:
            if _known_change(previous["server_connected"], client_view["server_connected"]):
                connected = client_view["server_connected"]
                if self._notify(
                    "UrBackup server connected" if connected else "UrBackup server lost",
                    status["decision"]["reason"],
                    status,
                ):
                    self._previous_client = client_view
                return
            if _known_change(previous["backup_running"], client_view["backup_running"]):
                summary, body = state.notify_summary(status)
                if self._notify(summary, body, status):
                    self._previous_client = client_view
                return

        self._previous_client = client_view
        self._report_periodic(status)

    def _report_periodic(self, status: dict) -> None:
        now = time.monotonic()
        running = status["urbackup_client"]["backup_running"]
        if running:
            due = now - self._last_progress_notify >= self._config.progress_notify_seconds
        else:
            due = now - self._last_idle_notify >= self._config.idle_notify_seconds
        if not due:
            return
        if running:
            self._last_progress_notify = now
        else:
            self._last_idle_notify = now
        summary, body = state.notify_summary(status)
        self._notify(summary, body, status)

    def _notify(self, summary: str, body: str, status: dict) -> bool:
        """Send a notification from a worker thread, since the call blocks.

        Returns whether it went out. A notification that blocks on screen keeps
        the next one from being sent, and the caller has to know that so the
        state change is not booked as reported.
        """
        if self._notify_in_flight:
            print(
                f"notification held back, one is still open: {summary}",
                file=sys.stderr,
            )
            return False
        self._notify_in_flight = True

        actions = {ui.ACTION_DETAILS: "Details"}
        if status["decision"]["user_enabled"]:
            actions[ui.ACTION_DEACTIVATE] = "Deactivate"
        else:
            actions[ui.ACTION_ACTIVATE] = "Activate"

        timeout = self._config.notify_timeout_seconds
        threading.Thread(
            target=self._notify_worker,
            args=(summary, body, timeout, actions),
            daemon=True,
        ).start()
        return True

    def _notify_worker(
        self, summary: str, body: str, timeout: int, actions: dict[str, str]
    ) -> None:
        try:
            chosen = ui.notify(summary, body, timeout, actions)
            if chosen == ui.ACTION_DETAILS:
                self._requests.put(ui.ACTION_DETAILS)
            elif chosen == ui.ACTION_ACTIVATE:
                runtime.set_user_enabled(True)
            elif chosen == ui.ACTION_DEACTIVATE:
                runtime.set_user_enabled(False)
            if chosen is not None:
                self._wake.set()
        finally:
            self._notify_in_flight = False

    # -- status window -----------------------------------------------------

    def _drain_requests(self) -> None:
        while True:
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return
            if request == ui.ACTION_DETAILS and self._window is None:
                self._open_window()

    def _open_window(self) -> None:
        try:
            self._window = ui.StatusWindow()
        except OSError as error:
            print(f"cannot open status window: {error}", file=sys.stderr)
            self._window = None

    def _refresh_window(self, status: dict) -> None:
        if self._window is None:
            return
        if not self._window.update(state.format_status(status)):
            self._close_window()

    def _close_window(self) -> None:
        if self._window is None:
            return
        self._window.close()
        self._window = None


def main() -> int:
    try:
        config = load()
    except ConfigError as error:
        return _fail_safe(str(error))

    try:
        runtime.check_directory()
    except runtime.RuntimeDirError as error:
        print(error, file=sys.stderr)
        return 1

    daemon = Daemon(config)
    for received in (signal.SIGTERM, signal.SIGINT):
        signal.signal(received, lambda *_: daemon.request_stop())
    return daemon.run()


def _fail_safe(message: str) -> int:
    """Keep the client stopped and tell the user what is broken."""
    print(f"configuration error: {message}", file=sys.stderr)
    try:
        if client.is_active() is not False:
            client.stop()
    except client.ControlError as error:
        print(f"cannot stop {client.UNIT}: {error}", file=sys.stderr)
    if ui.yad_available():
        ui.error_dialog(
            "urbackup-gated cannot run:\n\n"
            f"{message}\n\n"
            "The UrBackup client stays stopped. Fix the configuration and start "
            "the service again, or start the client by hand if you need a backup now."
        )
    return EX_CONFIG


if __name__ == "__main__":
    sys.exit(main())
