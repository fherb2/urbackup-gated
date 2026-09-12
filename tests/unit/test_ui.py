"""The desktop side: what it builds, and what it says when it fails.

A failing notify-send used to be indistinguishable from "nobody clicked
anything" - no output, no exit code looked at, nothing in the journal. The
cases are not exotic: no display, no session bus, a notify-send too old for
--action.
"""

import contextlib
import io
import os
import unittest

import support
from urbackup_gated import ui


class FailingPrograms(support.StubbedCase):
    """Stand-ins that fail the way the real programs fail."""

    def _program(self, name: str, body: str) -> str:
        path = self.tmp / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return str(path)

    def _capture(self, call) -> str:
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.result = call()
        return captured.getvalue()

    def test_a_failing_notify_send_is_reported(self):
        self.patch(ui, "NOTIFY_SEND",
                   self._program("bad-notify", 'echo "no display" >&2\nexit 1\n'))
        err = self._capture(lambda: ui.notify("s", "b", 5, {ui.ACTION_DETAILS: "Details"}))
        self.assertIn("no display", err)
        self.assertIsNone(self.result)

    def test_a_missing_notify_send_is_reported(self):
        self.patch(ui, "NOTIFY_SEND", str(self.tmp / "not-there"))
        err = self._capture(lambda: ui.notify("s", "b", 5, {}))
        self.assertIn("notification failed", err)
        self.assertIsNone(self.result)

    def test_a_successful_notification_stays_quiet(self):
        self.patch(ui, "NOTIFY_SEND", self._program("ok-notify", "exit 0\n"))
        err = self._capture(lambda: ui.notify("s", "b", 5, {}))
        self.assertEqual(err, "")

    def test_a_chosen_action_is_returned(self):
        self.patch(ui, "NOTIFY_SEND",
                   self._program("acting-notify", "echo details\nexit 0\n"))
        self._capture(lambda: ui.notify("s", "b", 5, {ui.ACTION_DETAILS: "Details"}))
        self.assertEqual(self.result, ui.ACTION_DETAILS)

    def test_a_failing_error_dialog_is_reported(self):
        # The one that matters most: this dialog exists to explain a broken
        # state. Failing silently means the user learns nothing at all.
        self.patch(ui, "YAD", self._program("bad-yad", 'echo "cannot open display" >&2\nexit 1\n'))
        err = self._capture(lambda: ui.error_dialog("something is broken"))
        self.assertIn("cannot open display", err)

    def test_a_successful_error_dialog_stays_quiet(self):
        self.patch(ui, "YAD", self._program("ok-yad", "exit 0\n"))
        err = self._capture(lambda: ui.error_dialog("something is broken"))
        self.assertEqual(err, "")


class CommandLine(support.StubbedCase):
    """The arguments actually built, recorded by a stand-in."""

    def setUp(self) -> None:
        super().setUp()
        self.log = self.tmp / "notify.log"
        path = self.tmp / "recording-notify"
        path.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >>"$LOG"\nexit 0\n')
        path.chmod(0o755)
        self.patch(ui, "NOTIFY_SEND", str(path))
        os.environ["LOG"] = str(self.log)
        self.addCleanup(os.environ.pop, "LOG", None)

    def test_actions_are_passed_as_key_equals_label(self):
        with contextlib.redirect_stderr(io.StringIO()):
            ui.notify("summary", "body", 5,
                      {ui.ACTION_DETAILS: "Details", ui.ACTION_DEACTIVATE: "Deactivate"})
        line = self.log.read_text()
        self.assertIn("--action details=Details", line)
        self.assertIn("--action deactivate=Deactivate", line)

    def test_the_timeout_is_passed_in_milliseconds(self):
        with contextlib.redirect_stderr(io.StringIO()):
            ui.notify("summary", "body", 5, {})
        self.assertIn("--expire-time 5000", self.log.read_text())


class Availability(support.StubbedCase):
    def test_a_missing_yad_is_detected(self):
        self.patch(ui, "YAD", "definitely-not-a-program-on-this-system")
        self.assertFalse(ui.yad_available())

    def test_a_present_program_is_detected(self):
        self.patch(ui, "YAD", "sh")
        self.assertTrue(ui.yad_available())


if __name__ == "__main__":
    unittest.main()
