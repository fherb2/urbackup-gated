"""The status tool: what it shows, and what it refuses to show.

Two of its properties are prescribed and were covered by nothing: that it states
how old the status is, and that it rejects a file whose schema it does not
understand instead of displaying it wrongly.
"""

import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone

import support
from urbackup_gated import cli, runtime, state


def _document(written_at=None, schema_version=None):
    """A minimal status document, good enough for the tool to render."""
    return {
        "schema_version": state.SCHEMA_VERSION if schema_version is None else schema_version,
        "written_at": written_at
        or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "network": {"connections": [], "any_connection": False,
                    "forbidden_wifi": False, "error": None},
        "decision": {"network_allows": None, "user_enabled": True,
                     "effective": None, "reason": "no network connection"},
        "urbackup_client": {"unit_active": False, "raw_available": False,
                            "server_connected": None, "backup_running": None,
                            "action": None, "done_bytes": None,
                            "total_bytes": None, "speed_bpms": None},
    }


class Age(unittest.TestCase):
    """The tool reads a file the daemon wrote; how stale it is, is the point."""

    def _age_of(self, delta: timedelta) -> str:
        moment = datetime.now(timezone.utc).astimezone() - delta
        return cli._age(moment.isoformat(timespec="seconds"))

    def test_seconds_are_shown_as_seconds(self):
        self.assertIn("s ago", self._age_of(timedelta(seconds=20)))

    def test_longer_spans_are_shown_as_minutes(self):
        self.assertIn("min ago", self._age_of(timedelta(minutes=7)))

    def test_a_timestamp_in_the_future_is_called_out(self):
        # Not cosmetic: it means the clock moved, and every age is then wrong.
        self.assertIn("future", self._age_of(timedelta(seconds=-60)))

    def test_an_unreadable_timestamp_does_not_crash(self):
        self.assertEqual(cli._age("not a timestamp"), "unknown")


class StatusOutput(support.StubbedCase):
    def _run_status(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli._status()
        return code, out.getvalue(), err.getvalue()

    def test_the_age_of_the_status_is_shown(self):
        runtime.write_state(_document())
        code, out, _err = self._run_status()
        self.assertEqual(code, 0)
        self.assertIn("last written", out)

    def test_a_foreign_schema_version_is_refused(self):
        # The version exists so the tool can say "I do not understand this"
        # rather than render a document whose fields may mean something else.
        runtime.write_state(_document(schema_version=state.SCHEMA_VERSION + 99))
        code, out, err = self._run_status()
        self.assertEqual(code, 1)
        self.assertIn("schema version", err)
        self.assertEqual(out, "")

    def test_a_missing_status_file_points_at_the_service(self):
        code, out, err = self._run_status()
        self.assertEqual(code, 1)
        self.assertIn("urbackup-gated", err)
        self.assertEqual(out, "")

    def test_an_unparsable_status_file_is_refused(self):
        runtime.STATE_FILE.write_text("{ not json")
        code, _out, err = self._run_status()
        self.assertEqual(code, 1)
        self.assertIn("no status available", err)


class ManualSwitch(support.StubbedCase):
    def _run(self, enabled: bool):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli._set_enabled(enabled)
        return code, out.getvalue(), err.getvalue()

    def test_deactivating_writes_the_flag(self):
        code, out, _err = self._run(False)
        self.assertEqual(code, 0)
        self.assertFalse(runtime.read_user_enabled())
        self.assertIn("deactivated", out)

    def test_activating_writes_the_flag(self):
        runtime.set_user_enabled(False)
        code, out, _err = self._run(True)
        self.assertEqual(code, 0)
        self.assertTrue(runtime.read_user_enabled())
        self.assertIn("activated", out)

    def test_a_missing_runtime_directory_is_reported(self):
        self.patch(runtime, "RUNTIME_DIR", self.tmp / "nowhere")
        code, _out, err = self._run(False)
        self.assertEqual(code, 1)
        self.assertIn("nowhere", err)


class Documents(unittest.TestCase):
    def test_the_helper_document_matches_the_real_schema(self):
        # A fixture that drifts from the real document would make every test
        # above pass against something the daemon never writes.
        self.assertEqual(
            set(_document()),
            {"schema_version", "written_at", "network", "decision", "urbackup_client"},
        )
        self.assertEqual(json.loads(json.dumps(_document()))["decision"].keys(),
                         {"network_allows", "user_enabled", "effective", "reason"})


if __name__ == "__main__":
    unittest.main()
