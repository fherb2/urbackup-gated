"""Command line tool: read the status, or set the manual flag."""

import argparse
import os
import sys
from datetime import datetime

from . import runtime, state


def _age(written_at: str) -> str:
    try:
        written = datetime.fromisoformat(written_at)
    except ValueError:
        return "unknown"
    seconds = (datetime.now(written.tzinfo) - written).total_seconds()
    if seconds < 0:
        return "in the future - check the clock"
    if seconds < 90:
        return f"{seconds:.0f} s ago"
    return f"{seconds / 60:.0f} min ago"


def _status() -> int:
    document = runtime.read_state()
    if document is None:
        print(
            f"no status available - {runtime.STATE_FILE} is missing or unreadable.\n"
            "Is urbackup-gated running? Check with: "
            "systemctl --user status urbackup-gated",
            file=sys.stderr,
        )
        return 1
    if document.get("schema_version") != state.SCHEMA_VERSION:
        print(
            f"{runtime.STATE_FILE} has schema version "
            f"{document.get('schema_version')!r}, expected {state.SCHEMA_VERSION} - "
            "the daemon and this tool are out of step",
            file=sys.stderr,
        )
        return 1
    print(state.format_status(document))
    print()
    print(state.field("last written", _age(document["written_at"])))
    return 0


def _set_enabled(enabled: bool) -> int:
    # Running this under sudo is an easy slip and an expensive one: the command
    # file would end up owned by root with mode 0600, the daemon could not read
    # it, would read that as "deactivated" and say so in the journal on every
    # tick. It heals with the next call as the right user - but until then the
    # machine does not back up and the reason is not obvious. Reading the status
    # as root is harmless, so only this way out is refused.
    if os.geteuid() == 0:
        print(
            "refusing to run as root: the flag belongs to the user the service "
            "runs for. Run this without sudo.",
            file=sys.stderr,
        )
        return 1
    try:
        runtime.check_directory()
        runtime.set_user_enabled(enabled)
    except (runtime.RuntimeDirError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    if enabled:
        print("activated - backups run again as soon as the network allows it")
    else:
        print("deactivated - the client is stopped until you activate it again")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="urbackup-gated-ctl",
        description="Query urbackup-gated, or allow and forbid backups by hand.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status", help="show the current status")
    subcommands.add_parser("activate", help="withdraw a manual deactivation")
    subcommands.add_parser(
        "deactivate", help="stop the client until it is activated again"
    )

    arguments = parser.parse_args()
    if arguments.command == "status":
        return _status()
    return _set_enabled(arguments.command == "activate")


if __name__ == "__main__":
    sys.exit(main())
