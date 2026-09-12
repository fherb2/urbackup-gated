"""Discovery of all currently active network connections via nmcli."""

import os
import subprocess
from dataclasses import dataclass

ETHERNET = "ethernet"
WIFI = "wifi"

# Only these carry backup traffic in a way we judge; tunnels and virtual
# devices are deliberately out of scope.
PHYSICAL_KINDS = frozenset({ETHERNET, WIFI})

_NMCLI = "nmcli"
_CONNECTED = "connected"


class NetworkQueryError(Exception):
    """nmcli could not be queried."""


@dataclass(frozen=True)
class Connection:
    device: str
    kind: str
    name: str
    ssid: str | None


def _run(*arguments: str) -> str:
    # LC_ALL=C is required, not merely helpful: nmcli's manual states that its
    # output is locale dependent and recommends exactly this for stable parsing.
    environment = dict(os.environ, LC_ALL="C")
    try:
        result = subprocess.run(
            [_NMCLI, "-t", *arguments],
            capture_output=True,
            text=True,
            env=environment,
            timeout=10,
            check=True,
        )
    except FileNotFoundError:
        raise NetworkQueryError("nmcli not found") from None
    except subprocess.TimeoutExpired:
        raise NetworkQueryError("nmcli timed out") from None
    except subprocess.CalledProcessError as error:
        raise NetworkQueryError(f"nmcli failed: {error.stderr.strip()}") from None
    return result.stdout


def _split_terse(line: str) -> list[str]:
    """Split one -t output line, honouring nmcli's backslash escaping.

    Values may legitimately contain ':' (SSIDs in particular); nmcli escapes
    those as '\\:', so a plain split would tear such a value apart.
    """
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


def _active_ssids() -> set[str]:
    # --rescan no keeps this from triggering a wifi scan, which would otherwise
    # happen on every tick.
    output = _run("-f", "ACTIVE,SSID", "device", "wifi", "list", "--rescan", "no")
    ssids = set()
    for line in output.splitlines():
        if not line:
            continue
        fields = _split_terse(line)
        if len(fields) >= 2 and fields[0] == "yes" and fields[1]:
            ssids.add(fields[1])
    return ssids


def active_connections() -> tuple[Connection, ...]:
    """Return every connected device, with the SSID filled in for wifi."""
    output = _run("-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")
    ssids = None
    connections = []
    for line in output.splitlines():
        if not line:
            continue
        fields = _split_terse(line)
        if len(fields) < 4:
            continue
        device, kind, state, name = fields[0], fields[1], fields[2], fields[3]
        # Not an equality check: nmcli also reports "connected (externally)" for
        # devices brought up outside NetworkManager, and "(site only)" or
        # "(local only)" for limited reachability. All of them are connected. A
        # wifi association made by wpa_supplicant would otherwise go unjudged -
        # and next to an ethernet link that would read as "allowed", which is
        # the one outcome the decision rules exist to prevent. "disconnected"
        # and "connecting" do not start with the word, so they still fall out.
        if not state.startswith(_CONNECTED) or kind == "loopback":
            continue
        ssid = None
        if kind == WIFI:
            if ssids is None:
                ssids = _active_ssids()
            # With a single wifi device the active SSID is unambiguous. The
            # profile name is not used as a fallback: it can be renamed freely
            # and would then silently pass the allow list.
            ssid = next(iter(ssids)) if len(ssids) == 1 else (name if name in ssids else None)
        connections.append(Connection(device=device, kind=kind, name=name, ssid=ssid))
    return tuple(connections)
