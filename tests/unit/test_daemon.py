"""What the daemon reports, and what it deliberately stays quiet about.

An unreachable UrBackup backend leaves the client flags unknown rather than
false. Treating that as a state change turned every gated stop into a second,
untrue message about a lost server connection one tick later.
"""

import threading
import time
import unittest

import support

support.ensure_watchdog()

from urbackup_gated import daemon, state, ui  # noqa: E402


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
        """One pass of the main loop: gather, act, report."""
        status = state.gather(self.config)
        action = self.daemon._apply(status)
        if action is not None:
            status["urbackup_client"]["unit_active"] = action == "started"
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
