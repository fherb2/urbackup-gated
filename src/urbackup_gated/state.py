"""The single place where the full status is gathered and judged.

Every consumer - the daemon, the live status window and the command line tool -
goes through here, so the decision and its wording exist exactly once.
"""

from datetime import datetime, timezone

from . import client, network, runtime
from .config import Config

SCHEMA_VERSION = 1

LABEL_WIDTH = 18


def _network_view(config: Config) -> tuple[dict, bool | None, str]:
    try:
        connections = network.active_connections()
    except network.NetworkQueryError as error:
        view = {
            "connections": [],
            "any_connection": False,
            "forbidden_wifi": False,
            "error": str(error),
        }
        return view, False, f"network state unknown ({error})"

    physical = [c for c in connections if c.kind in network.PHYSICAL_KINDS]
    entries = []
    forbidden = []
    for connection in physical:
        allowed = None
        if connection.kind == network.WIFI:
            allowed = connection.ssid in config.allowed_ssids
            if not allowed:
                forbidden.append(connection.ssid or connection.name)
        entries.append(
            {
                "device": connection.device,
                "kind": connection.kind,
                "name": connection.name,
                "ssid": connection.ssid,
                "allowed": allowed,
            }
        )

    view = {
        "connections": entries,
        "any_connection": bool(physical),
        "forbidden_wifi": bool(forbidden),
        "error": None,
    }

    if forbidden:
        names = ", ".join(f"'{name}'" for name in forbidden)
        return view, False, f"wifi {names} is not on the allow list"
    if not physical:
        return view, None, "no network connection - client left as it is"
    kinds = ", ".join(sorted({c.kind for c in physical}))
    return view, True, f"allowed connection active ({kinds})"


def gather(config: Config) -> dict:
    """Collect network state, user flag and client status into one document."""
    network_view, network_allows, network_reason = _network_view(config)
    user_enabled = runtime.read_user_enabled()
    client_status = client.status()

    if not user_enabled:
        effective: bool | None = False
        reason = "manually deactivated"
    elif network_allows is None:
        effective = None
        reason = network_reason
    else:
        effective = network_allows
        reason = network_reason

    return {
        "schema_version": SCHEMA_VERSION,
        "written_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "network": network_view,
        "decision": {
            "network_allows": network_allows,
            "user_enabled": user_enabled,
            "effective": effective,
            "reason": reason,
        },
        "urbackup_client": {
            "unit_active": client_status.unit_active,
            "raw_available": client_status.raw_available,
            "server_connected": client_status.server_connected,
            "backup_running": client_status.backup_running,
            "action": client_status.action,
            "done_bytes": client_status.done_bytes,
            "total_bytes": client_status.total_bytes,
            "speed_bpms": client_status.speed_bpms,
        },
    }


def _yes_no_unknown(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def field(label: str, value: object) -> str:
    """One aligned label/value line, shared by the window and the CLI."""
    return f"  {label + ':':<{LABEL_WIDTH}}{value}"


def _progress_text(client_view: dict) -> str | None:
    done = client_view.get("done_bytes")
    total = client_view.get("total_bytes")
    if not isinstance(total, (int, float)) or total <= 0:
        return None
    done = done if isinstance(done, (int, float)) else 0
    percent = done * 100.0 / total
    text = f"{done / 2**20:.0f} of {total / 2**20:.0f} MiB ({percent:.1f} %)"
    speed = client_view.get("speed_bpms")
    if isinstance(speed, (int, float)) and speed > 0:
        text += f", {speed / 1000:.2f} MB/s"
    return text


def format_status(status: dict) -> str:
    """Render the status document as the plain text shown to the user."""
    decision = status["decision"]
    network_view = status["network"]
    client_view = status["urbackup_client"]

    lines = [
        f"urbackup-gated - status of {status['written_at']}",
        "",
        "Decision",
        field("backup allowed", _yes_no_unknown(decision["effective"])),
        field("reason", decision["reason"]),
        field("network allows", _yes_no_unknown(decision["network_allows"])),
        field("user enabled", _yes_no_unknown(decision["user_enabled"])),
        "",
        "Network",
    ]

    if network_view["error"]:
        lines.append(field("error", network_view["error"]))
    elif not network_view["connections"]:
        lines.append("  no active connection")
    else:
        for entry in network_view["connections"]:
            label = entry["ssid"] or entry["name"]
            suffix = ""
            if entry["allowed"] is not None:
                suffix = "  [allowed]" if entry["allowed"] else "  [not allowed]"
            lines.append(f"  {entry['kind']:<9} {entry['device']:<10} {label}{suffix}")

    lines += [
        "",
        "UrBackup client",
        field("service active", _yes_no_unknown(client_view["unit_active"])),
    ]
    if not client_view["raw_available"]:
        # A unit we stopped ourselves cannot answer, and guessing at the reason
        # would dress our own doing up as a diagnosis. The guess is worth
        # printing in the other two cases only: if the unit runs and the backend
        # still says nothing, that is the one genuinely odd thing in the whole
        # output, and if the unit state could not even be asked, the guess is
        # the best statement left - a dash there would claim a certainty we do
        # not have.
        if client_view["unit_active"] is False:
            lines.append(field("status", "-"))
        else:
            lines.append(field("status", "not reachable (backend not running?)"))
    else:
        lines.append(field("server connected", _yes_no_unknown(client_view["server_connected"])))
        lines.append(field("backup running", _yes_no_unknown(client_view["backup_running"])))
        if client_view["action"]:
            lines.append(field("action", client_view["action"]))
        progress = _progress_text(client_view)
        if progress:
            lines.append(field("progress", progress))

    return "\n".join(lines)


def notify_summary(status: dict) -> tuple[str, str]:
    """Short summary and body for a desktop notification."""
    decision = status["decision"]
    client_view = status["urbackup_client"]

    if client_view["backup_running"]:
        summary = f"UrBackup: backup running ({client_view['action']})"
        return summary, _progress_text(client_view) or "no progress figures yet"

    if decision["effective"]:
        summary = "UrBackup: idle"
        connected = _yes_no_unknown(client_view["server_connected"])
        return summary, f"server connected: {connected}"

    return "UrBackup: not backing up", decision["reason"]
