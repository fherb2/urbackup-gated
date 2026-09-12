"""Desktop notifications and the live status window."""

import shutil
import subprocess
import sys

NOTIFY_SEND = "notify-send"
YAD = "yad"

ACTION_DETAILS = "details"
ACTION_ACTIVATE = "activate"
ACTION_DEACTIVATE = "deactivate"

_APP_NAME = "urbackup-gated"

# yad clears its text view when a line starts with a form feed, but discards the
# rest of that same line. The replacement text must therefore follow as its own
# line (found in yad's handle_stdin(), src/text.c).
_CLEAR = "\f\n"


def yad_available() -> bool:
    return shutil.which(YAD) is not None


def notify(summary: str, body: str, timeout_seconds: int, actions: dict[str, str]) -> str | None:
    """Show a notification and block until it is clicked or times out.

    Returns the key of the chosen action, or None if none was chosen. Passing
    actions implies --wait, which is why callers must not run this in the main
    loop.
    """
    command = [
        NOTIFY_SEND,
        "--app-name",
        _APP_NAME,
        "--expire-time",
        str(timeout_seconds * 1000),
    ]
    for key, label in actions.items():
        command += ["--action", f"{key}={label}"]
    command += [summary, body]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"notification failed: {error}", file=sys.stderr)
        return None
    # Without this, every real failure looks like "no action chosen": no display,
    # no session bus, or a notify-send too old to know --action. The user sees
    # nothing, and the journal would have said nothing either.
    if result.returncode != 0:
        print(
            f"{NOTIFY_SEND} failed with code {result.returncode}: "
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    chosen = result.stdout.strip()
    return chosen or None


def error_dialog(message: str) -> None:
    """Show a blocking error window that has to be acknowledged."""
    command = [
        YAD,
        "--title",
        "urbackup-gated",
        "--image",
        "dialog-error",
        "--width",
        "480",
        "--text",
        message,
        "--button",
        "OK:0",
    ]
    try:
        # Output is captured only so a failure can be reported; yad draws its
        # window regardless.
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"error dialog failed: {error}", file=sys.stderr)
        return
    # A non-zero code here is not the user clicking something away - the only
    # button is OK, which exits 0. It means yad never got to show anything, and
    # that is precisely the moment the user is owed an explanation.
    if result.returncode != 0:
        print(
            f"{YAD} failed with code {result.returncode}: {result.stderr.strip()}",
            file=sys.stderr,
        )


class StatusWindow:
    """A yad text window that is rewritten in place until the user closes it."""

    def __init__(self) -> None:
        self._process = subprocess.Popen(
            [
                YAD,
                "--text-info",
                "--listen",
                "--title",
                "urbackup-gated",
                "--width",
                "560",
                "--height",
                "420",
                "--fontname",
                "monospace 10",
                "--button",
                "Close:0",
            ],
            stdin=subprocess.PIPE,
            text=True,
        )

    @property
    def closed(self) -> bool:
        return self._process.poll() is not None

    def update(self, text: str) -> bool:
        """Replace the window content. Returns False once the window is gone."""
        if self._process.stdin is None:
            return False
        try:
            self._process.stdin.write(_CLEAR)
            self._process.stdin.write(text + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, ValueError):
            return False
        return not self.closed

    def close(self) -> None:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except (BrokenPipeError, ValueError):
                pass
        if self._process.poll() is None:
            self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
