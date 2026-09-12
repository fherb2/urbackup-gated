"""The runtime directory: status file, user flag and trigger files."""

import json
import os
import sys
import tempfile
from pathlib import Path

RUNTIME_DIR = Path("/run/urbackup-gated")
STATE_FILE = RUNTIME_DIR / "state.json"
USER_ENABLED_FILE = RUNTIME_DIR / "user-enabled"
NETWORK_EVENT_FILE = RUNTIME_DIR / "network-event"

# The directory is watched as a whole, so the daemon's own state.json writes
# would otherwise wake it in an endless loop.
WATCHED_NAMES = frozenset({USER_ENABLED_FILE.name, NETWORK_EVENT_FILE.name})

_ENABLED = "enabled"
_DISABLED = "disabled"


class RuntimeDirError(Exception):
    """The runtime directory is missing or not writable."""


def check_directory() -> None:
    if not RUNTIME_DIR.is_dir():
        raise RuntimeDirError(
            f"{RUNTIME_DIR} does not exist - is the tmpfiles.d snippet installed?"
        )
    if not os.access(RUNTIME_DIR, os.W_OK):
        raise RuntimeDirError(f"{RUNTIME_DIR} is not writable")


def write_atomic(path: Path, text: str) -> None:
    """Replace a file's content indivisibly, so readers never see a partial write."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            # NamedTemporaryFile creates with 0600 and os.replace keeps that, so
            # the files ended up unreadable for everyone but the service user -
            # while the directory is 0755 and both the tmpfiles comment and the
            # documentation promise they can be read. Writing is governed by the
            # directory, so this gives nothing away.
            os.fchmod(handle.fileno(), 0o644)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def read_user_enabled() -> bool:
    """Read the manual flag; an absent file means enabled, anything odd disabled."""
    try:
        content = USER_ENABLED_FILE.read_text().strip()
    except FileNotFoundError:
        return True
    except OSError as error:
        print(f"cannot read {USER_ENABLED_FILE}: {error}", file=sys.stderr)
        return False
    if content == _ENABLED:
        return True
    if content == _DISABLED:
        return False
    print(
        f"{USER_ENABLED_FILE} holds {content!r}, treating as {_DISABLED}",
        file=sys.stderr,
    )
    return False


def set_user_enabled(enabled: bool) -> None:
    write_atomic(USER_ENABLED_FILE, f"{_ENABLED if enabled else _DISABLED}\n")


def clear_user_enabled() -> None:
    USER_ENABLED_FILE.unlink(missing_ok=True)


def write_state(status: dict) -> None:
    write_atomic(STATE_FILE, json.dumps(status, indent=2) + "\n")


def read_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
