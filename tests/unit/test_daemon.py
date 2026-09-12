"""What the daemon reports, and what it deliberately stays quiet about.

An unreachable UrBackup backend leaves the client flags unknown rather than
false. Treating that as a state change turned every gated stop into a second,
untrue message about a lost server connection one tick later.
"""

import contextlib
import io
import threading
import time
import unittest

import support

support.ensure_watchdog()

from urbackup_gated import daemon, runtime, state, ui  # noqa: E402


class ReportingCase(support.StubbedCase):
    """A daemon whose notifications are recorded instead of being shown."""

    scenario = "ethernet_only"

    def setUp(self) -> None:
        super().setUp()
        self.notifications: list[tuple[str, str]] = []
        self.patch(ui, "notify", self._record)

        # The client is already running, so the network verdict alone never
        # makes the daemon act and the notifications under test stay isolated.
        self.set_client_state(active=True)

        self.config = self.load_config()
        self.daemon = daemon.Daemon(self.config)
        # run() does this before entering the loop; without it the very first
        # tick would already be due for a periodic reminder.
        now = time.monotonic()
        self.daemon._last_idle_notify = now
        self.daemon._last_progress_notify = now

    def _record(self, summary, body, timeout, actions):
        self.notifications.append((summary, body))
        return None

    def backend(self, reachable: bool, **fields) -> None:
        """Answer like the real client: JSON while its backend runs, an error line otherwise."""
        if reachable:
            self.set_client_status(
                {"internet_connected": True, "servers": ["test-server"], **fields}
            )
        else:
            (self.scenario_dir / "client_status.json").unlink(missing_ok=True)

    def tick(self) -> str | None:
        """One pass of the main loop, everything but the waiting."""
        status = state.gather(self.config)
        action = self.daemon._apply(status)
        if action is not None:
            status["urbackup_client"]["unit_active"] = action == "started"
        runtime.write_state(status)
        self.daemon._refresh_window(status)
        self.daemon._report(status, action)
        for thread in threading.enumerate():
            if thread is not threading.current_thread():
                thread.join(timeout=5)
        return action

    def summaries(self) -> list[str]:
        return [summary for summary, _body in self.notifications]


class UnknownIsNotAChange(ReportingCase):
    def test_a_vanishing_backend_reports_no_server_loss(self):
        self.backend(True)
        self.tick()
        self.notifications.clear()

        self.backend(False)
        self.tick()
        self.assertEqual(self.summaries(), [])

    def test_a_vanishing_backend_reports_no_backup_change_either(self):
        # Both flags go unknown together, so guarding only the server flag
        # would merely move the false message to the backup one.
        self.backend(True, running_processes=[{"action": "INCR"}])
        self.tick()
        self.notifications.clear()

        self.backend(False)
        self.tick()
        self.assertEqual(self.summaries(), [])

    def test_a_returning_backend_reports_nothing_by_itself(self):
        self.backend(False)
        self.tick()
        self.notifications.clear()

        self.backend(True)
        self.tick()
        self.assertEqual(self.summaries(), [])


class RealChangesAreStillReported(ReportingCase):
    def test_a_server_loss_while_the_backend_answers(self):
        self.backend(True)
        self.tick()
        self.notifications.clear()

        self.set_client_status({"internet_connected": False, "servers": []})
        self.tick()
        self.assertEqual(len(self.notifications), 1)
        self.assertIn("lost", self.summaries()[0])

    def test_a_server_coming_back_while_the_backend_answers(self):
        self.set_client_status({"internet_connected": False, "servers": []})
        self.tick()
        self.notifications.clear()

        self.backend(True)
        self.tick()
        self.assertEqual(len(self.notifications), 1)
        self.assertIn("connected", self.summaries()[0])

    def test_a_backup_starting_while_the_backend_answers(self):
        self.backend(True)
        self.tick()
        self.notifications.clear()

        self.backend(True, running_processes=[{"action": "INCR"}])
        self.tick()
        self.assertEqual(len(self.notifications), 1)
        self.assertIn("INCR", self.summaries()[0])


class GatedStop(ReportingCase):
    def test_a_gated_stop_is_reported_once(self):
        # The sequence that produced the false report: the client runs over
        # ethernet, a forbidden wifi appears, the daemon stops the client, and
        # the backend goes away with it.
        self.backend(True)
        self.tick()
        self.notifications.clear()

        self.use_scenario("forbidden_wifi")
        self.set_client_state(active=True)
        self.backend(True)
        self.assertEqual(self.tick(), "stopped")

        self.backend(False)
        self.tick()

        self.assertEqual(self.summaries(), ["UrBackup client stopped"])


class StartupChecks(ReportingCase):
    """What run() does before and around the loop.

    The stop event is set beforehand, so the loop ends after its first pass and
    run() gets to its shutdown half. That makes the startup half observable.
    """

    def run_once(self) -> str:
        """Run the daemon through one pass and return what it wrote to stderr."""
        self.daemon.request_stop()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured), contextlib.redirect_stdout(io.StringIO()):
            self.daemon.run()
        return captured.getvalue()

    def test_a_missing_yad_is_reported(self):
        # Without this the one message that explains a broken state would be the
        # message that goes missing.
        self.patch(ui, "yad_available", lambda: False)
        self.assertIn("yad", self.run_once())

    def test_a_present_yad_is_not_reported(self):
        self.patch(ui, "yad_available", lambda: True)
        self.assertNotIn("yad", self.run_once())

    def test_the_manual_flag_is_cleared_at_startup(self):
        # "Activated at every service start" is implemented by deleting the file.
        from urbackup_gated import runtime

        runtime.set_user_enabled(False)
        self.patch(ui, "yad_available", lambda: True)
        self.run_once()
        self.assertFalse(runtime.USER_ENABLED_FILE.exists())


class BlockingNotification(ReportingCase):
    """A notification blocks until it is clicked or times out.

    If that call sat in the main loop, the whole check would stand still for as
    long as a notification hangs unanswered on screen.
    """

    def setUp(self) -> None:
        super().setUp()
        self.released = threading.Event()
        self.entered = threading.Event()
        self.patch(ui, "notify", self._blocking_notify)
        self.addCleanup(self.released.set)

    def _blocking_notify(self, summary, body, timeout, actions):
        self.notifications.append((summary, body))
        self.entered.set()
        self.released.wait(10)
        return None

    def test_a_held_back_change_is_retried_instead_of_lost(self):
        # The previous state used to move on regardless, so a change that could
        # not be sent was gone for good - not late, gone.
        self.backend(True)
        self.tick()
        self.notifications.clear()

        # First change: goes out and blocks on screen.
        self.set_client_status({"internet_connected": False, "servers": []})
        self.daemon._report(state.gather(self.config), None)
        self.assertTrue(self.entered.wait(5))
        self.assertEqual(len(self.notifications), 1)

        # Second change while the first still hangs: has to be held back.
        self.backend(True)
        self.daemon._report(state.gather(self.config), None)
        self.assertEqual(len(self.notifications), 1, "the second one slipped through")

        # Release the first; the second must still be pending, not forgotten.
        self.released.set()
        self._await_threads()
        self.daemon._report(state.gather(self.config), None)
        self._await_threads()
        self.assertEqual(len(self.notifications), 2, "the held-back change was lost")
        self.assertIn("connected", self.notifications[1][0])

    def _await_threads(self) -> None:
        for thread in threading.enumerate():
            if thread is not threading.current_thread():
                thread.join(timeout=5)

    def test_reporting_returns_while_the_notification_is_still_open(self):
        self.backend(True)
        self.tick()
        # A state change the daemon has to report, so a notification is sent.
        self.set_client_status({"internet_connected": False, "servers": []})
        status = state.gather(self.config)

        reported = threading.Event()

        def report():
            self.daemon._report(status, None)
            reported.set()

        threading.Thread(target=report, daemon=True).start()

        self.assertTrue(self.entered.wait(5), "the notification was never sent")
        # The decisive assertion: the notification is provably still hanging, and
        # the caller is already back. A synchronous notify would fail right here.
        self.assertTrue(
            reported.wait(5),
            "_report stayed inside the notification instead of handing it to a thread",
        )
        self.assertFalse(self.released.is_set(), "the notification ended by itself")

        self.released.set()


class PeriodicClocks(ReportingCase):
    """Both clocks restart on any message, not just the branch that was due."""

    def test_any_message_restarts_both_clocks(self):
        self.backend(True)
        # Pretend both are long overdue, then let a state change speak up.
        self.daemon._last_idle_notify = time.monotonic() - 100000
        self.daemon._last_progress_notify = time.monotonic() - 100000
        self.set_client_status({"internet_connected": False, "servers": []})
        self.tick()

        self.assertEqual(len(self.notifications), 1)
        # Had only the due branch been advanced, the other would still be
        # overdue and fire on the very next tick.
        self.notifications.clear()
        self.tick()
        self.assertEqual(self.summaries(), [])

    def test_a_held_back_message_does_not_restart_the_clocks(self):
        before = self.daemon._last_idle_notify
        self.daemon._notify_in_flight = True
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(self.daemon._notify("s", "b", state.gather(self.config)))
        self.assertEqual(self.daemon._last_idle_notify, before)


class UnknownUnitState(ReportingCase):
    """An unanswerable unit state has to fall on the safe side.

    Safe means "assume it runs": over a forbidden network that still attempts a
    stop, while the opposite assumption would leave a client backing up over a
    metered link with nobody to stop it.
    """

    scenario = "forbidden_wifi"

    def test_a_forbidden_network_still_attempts_the_stop(self):
        self.set_client_state(active=True)
        status = state.gather(self.config)
        status["urbackup_client"]["unit_active"] = None
        self.assertEqual(self.daemon._apply(status), "stopped")
        self.assertFalse(self.client_is_active())

    def test_an_allowed_network_does_not_start_on_a_guess(self):
        self.use_scenario("ethernet_only")
        self.set_client_state(active=False)
        status = state.gather(self.config)
        status["urbackup_client"]["unit_active"] = None
        self.assertIsNone(self.daemon._apply(status))
        self.assertFalse(self.client_is_active())


class _FakeWindow:
    """Stands in for the yad window: remembers what it was shown."""

    def __init__(self, alive: bool = True) -> None:
        self.texts: list[str] = []
        self.alive = alive
        self.closed_by_daemon = False

    def update(self, text: str) -> bool:
        self.texts.append(text)
        return self.alive

    def close(self) -> None:
        self.closed_by_daemon = True


class StatusWindowHandling(ReportingCase):
    """Opening, refreshing and closing, and what it does to the messages."""

    def test_the_details_button_opens_exactly_one_window(self):
        opened = []
        self.patch(ui, "StatusWindow", lambda: opened.append(_FakeWindow()) or opened[-1])
        self.daemon._requests.put(ui.ACTION_DETAILS)
        self.daemon._requests.put(ui.ACTION_DETAILS)
        self.daemon._drain_requests()
        self.assertEqual(len(opened), 1)

    def test_a_window_that_cannot_open_is_reported_and_not_remembered(self):
        def refuse():
            raise OSError("no display")

        self.patch(ui, "StatusWindow", refuse)
        self.daemon._requests.put(ui.ACTION_DETAILS)
        with contextlib.redirect_stderr(io.StringIO()) as captured:
            self.daemon._drain_requests()
        self.assertIn("no display", captured.getvalue())
        self.assertIsNone(self.daemon._window)

    def test_an_open_window_shortens_the_check_interval(self):
        # 30 seconds would make the window useless as a live display.
        self.assertEqual(self.daemon._interval(), self.config.check_seconds)
        self.daemon._window = _FakeWindow()
        self.assertEqual(self.daemon._interval(), self.config.check_seconds_window_open)

    def test_an_open_window_suppresses_the_messages(self):
        self.backend(True)
        self.tick()
        self.notifications.clear()

        self.daemon._window = _FakeWindow()
        self.set_client_status({"internet_connected": False, "servers": []})
        self.tick()
        self.assertEqual(self.summaries(), [], "messages repeat what is on screen")

    def test_the_window_receives_the_same_text_the_tool_shows(self):
        window = _FakeWindow()
        self.daemon._window = window
        self.backend(True)
        self.tick()
        self.assertEqual(len(window.texts), 1)
        self.assertIn("urbackup-gated - status of", window.texts[0])

    def test_a_closed_window_is_dropped(self):
        # Noticed by the write failing, so no back channel is needed.
        window = _FakeWindow(alive=False)
        self.daemon._window = window
        self.backend(True)
        self.tick()
        self.assertIsNone(self.daemon._window)
        self.assertTrue(window.closed_by_daemon)

    def test_messages_return_once_the_window_is_gone(self):
        self.backend(True)
        self.daemon._window = _FakeWindow(alive=False)
        self.tick()
        self.notifications.clear()

        self.set_client_status({"internet_connected": False, "servers": []})
        self.tick()
        self.assertEqual(len(self.notifications), 1)


class KnownChange(unittest.TestCase):
    def test_only_two_known_and_different_values_count(self):
        cases = {
            (True, False): True,
            (False, True): True,
            (True, True): False,
            (False, False): False,
            (True, None): False,
            (None, True): False,
            (False, None): False,
            (None, False): False,
            (None, None): False,
        }
        for (previous, current), expected in cases.items():
            with self.subTest(previous=previous, current=current):
                self.assertIs(daemon._known_change(previous, current), expected)


if __name__ == "__main__":
    unittest.main()
