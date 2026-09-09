"""Status and control of the UrBackup client backend service."""

import json
import subprocess
from dataclasses import dataclass

UNIT = "urbackupclientbackend.service"

_SYSTEMCTL = "/usr/bin/systemctl"
_SUDO = "/usr/bin/sudo"
_CLIENTCTL = "urbackupclientctl"


class ControlError(Exception):
    """A privileged systemctl call failed."""


@dataclass(frozen=True)
class ClientStatus:
    unit_active: bool
    raw_available: bool
    server_connected: bool | None
    backup_running: bool | None
    action: str | None
    done_bytes: int | None
    total_bytes: int | None
    speed_bpms: float | None


def _systemctl_query(verb: str) -> bool:
    result = subprocess.run(
        [_SYSTEMCTL, verb, "--quiet", UNIT],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def _systemctl_privileged(verb: str) -> None:
    # -n so a missing sudoers entry fails immediately instead of waiting for a
    # password nobody can type into a background service.
    result = subprocess.run(
        [_SUDO, "-n", _SYSTEMCTL, verb, UNIT],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ControlError(f"systemctl {verb} {UNIT} failed: {result.stderr.strip()}")


def is_active() -> bool:
    return _systemctl_query("is-active")


def is_enabled() -> bool:
    return _systemctl_query("is-enabled")


def start() -> None:
    _systemctl_privileged("start")


def stop() -> None:
    _systemctl_privileged("stop")


def disable() -> None:
    _systemctl_privileged("disable")


def _raw_status() -> dict | None:
    try:
        result = subprocess.run(
            [_CLIENTCTL, "status"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError:
        # The client prints a plain-text error line while its backend is down.
        return None
    return document if isinstance(document, dict) else None


def _running_process(document: dict) -> dict | None:
    processes = document.get("running_processes")
    if isinstance(processes, list) and processes:
        first = processes[0]
        return first if isinstance(first, dict) else None
    return document if document.get("action") else None


def _number(value: object) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def status() -> ClientStatus:
    """Collect everything known about the client, tolerating an absent backend."""
    unit_active = is_active()
    document = _raw_status()
    if document is None:
        return ClientStatus(
            unit_active=unit_active,
            raw_available=False,
            server_connected=None,
            backup_running=None,
            action=None,
            done_bytes=None,
            total_bytes=None,
            speed_bpms=None,
        )

    servers = document.get("servers")
    server_connected = bool(document.get("internet_connected")) or bool(
        isinstance(servers, list) and servers
    )

    process = _running_process(document)
    action = process.get("action") if process else None
    return ClientStatus(
        unit_active=unit_active,
        raw_available=True,
        server_connected=server_connected,
        backup_running=bool(action),
        action=action if isinstance(action, str) else None,
        done_bytes=_number(process.get("done_bytes")) if process else None,
        total_bytes=_number(process.get("total_bytes")) if process else None,
        speed_bpms=_number(process.get("speed_bpms")) if process else None,
    )
