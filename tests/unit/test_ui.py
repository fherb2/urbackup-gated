"""The desktop side: what it builds, and what it says when it fails.

A failing notify-send used to be indistinguishable from "nobody clicked
anything" - no output, no exit code looked at, nothing in the journal. The
cases are not exotic: no display, no session bus, a notify-send too old for
--action.
"""

import contextlib
import io
import os
import time
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


class LiveStatusWindow(support.StubbedCase):
    """The window is rewritten in place; it must not grow into a log.

    yad reads its standard input line by line and clears its buffer when a line
    begins with a form feed - but discards the rest of that same line. The text
    therefore has to follow as a line of its own. That rule was found in yad's
    own source and is the single most fragile detail here, and until now it was
    checked by nothing.
    """

    def setUp(self) -> None:
        super().setUp()
        self.transcript = self.tmp / "stdin.txt"
        self.marker = self.tmp / "close-now"
        stub = self.tmp / "recording-yad"
        # Writes every line it is given to a file and ends as soon as the marker
        # appears, which stands in for the user closing the window.
        stub.write_text(
            "#!/bin/sh\n"
            'while IFS= read -r line; do\n'
            '    printf "%s\\n" "$line" >>"$TRANSCRIPT"\n'
            '    [ -e "$CLOSE_MARKER" ] && exit 0\n'
            "done\n"
            "exit 0\n"
        )
        stub.chmod(0o755)
        self.patch(ui, "YAD", str(stub))
        os.environ["TRANSCRIPT"] = str(self.transcript)
        os.environ["CLOSE_MARKER"] = str(self.marker)
        self.addCleanup(os.environ.pop, "TRANSCRIPT", None)
        self.addCleanup(os.environ.pop, "CLOSE_MARKER", None)

    def _lines(self, expected: int) -> list[str]:
        """Wait until the stand-in has written at least that many lines.

        The stand-in is a separate process; reading the moment the file exists
        catches it mid-write and makes the test fail for the wrong reason.
        """
        # split("\n") and not splitlines(): the latter treats the form feed
        # itself as a line boundary, which would cut the transcript apart at
        # exactly the place under test.
        for _ in range(200):
            if self.transcript.exists():
                lines = self.transcript.read_text().split("\n")
                if len(lines) > expected:
                    return lines
            time.sleep(0.02)
        return self.transcript.read_text().split("\n") if self.transcript.exists() else []

    def test_the_form_feed_is_a_line_of_its_own(self):
        window = ui.StatusWindow()
        self.addCleanup(window.close)
        window.update("first line\nsecond line")

        lines = self._lines(2)
        self.assertIn("\f", lines[0])
        # The decisive part: nothing but the form feed on that line. Text after
        # it in the same line is thrown away by yad, so it would vanish.
        self.assertEqual(lines[0].strip("\f"), "")
        self.assertEqual(lines[1], "first line")

    def test_every_update_starts_with_a_clear(self):
        window = ui.StatusWindow()
        self.addCleanup(window.close)
        window.update("alpha")
        window.update("beta")

        lines = self._lines(4)
        self.assertEqual([i for i, l in enumerate(lines) if "\f" in l], [0, 2])
        self.assertEqual(lines[1], "alpha")
        self.assertEqual(lines[3], "beta")

    def test_a_closed_window_is_noticed(self):
        window = ui.StatusWindow()
        self.addCleanup(window.close)
        self.assertTrue(window.update("still open"))

        self.marker.touch()
        window.update("this one makes it exit")
        for _ in range(100):
            if window.closed:
                break
            time.sleep(0.02)
        # Whether it shows up as a broken pipe or as a process that is simply
        # gone depends on timing; either way update() has to report False.
        self.assertFalse(window.update("nobody is listening"))


class Availability(support.StubbedCase):
    def test_a_missing_yad_is_detected(self):
        self.patch(ui, "YAD", "definitely-not-a-program-on-this-system")
        self.assertFalse(ui.yad_available())

    def test_a_present_program_is_detected(self):
        self.patch(ui, "YAD", "sh")
        self.assertTrue(ui.yad_available())


if __name__ == "__main__":
    unittest.main()
