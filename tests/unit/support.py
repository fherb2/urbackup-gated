"""Shared setup for the unit tests.

The external commands are replaced by recording stubs on PATH rather than by
mocking subprocess: that way the command line the daemon actually builds is
part of what gets tested.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
SCENARIOS = TESTS_DIR / "scenarios"
STUBS = TESTS_DIR / "stubs"

sys.path.insert(0, str(REPO_ROOT / "src"))

from urbackup_gated import client, config, runtime  # noqa: E402

ALLOWED_SSIDS = ["lieluX", "home-net"]

_CONFIG_TEMPLATE = """allowed_ssids = {ssids}

[intervals]
check_seconds = 30
check_seconds_window_open = 5
idle_notify_seconds = 7200
progress_notify_seconds = 900

[notify]
timeout_seconds = 5
"""


class StubbedCase(unittest.TestCase):
    """Base case: stubbed commands, a private scenario copy, a private /run."""

    scenario: str | None = None

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="urbackup-gated-test."))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # A copy, so the committed fixtures stay pristine while the stubs write
        # their call logs and marker files.
        self.scenario_dir = self.tmp / "scenario"
        if self.scenario is None:
            self.scenario_dir.mkdir()
        else:
            shutil.copytree(SCENARIOS / self.scenario, self.scenario_dir)
        self._set_env("URBACKUP_GATED_SCENARIO", str(self.scenario_dir))
        self._set_env("PATH", f"{STUBS}{os.pathsep}{os.environ['PATH']}")

        # systemctl and sudo are absolute paths in production on purpose, so
        # PATH cannot shadow them. Point them at the stubs explicitly.
        self.patch(client, "_SYSTEMCTL", str(STUBS / "systemctl"))
        self.patch(client, "_SUDO", str(STUBS / "sudo"))

        self.runtime_dir = self.tmp / "run"
        self.runtime_dir.mkdir()
        self.patch(runtime, "RUNTIME_DIR", self.runtime_dir)
        self.patch(runtime, "STATE_FILE", self.runtime_dir / "state.json")
        self.patch(runtime, "USER_ENABLED_FILE", self.runtime_dir / "user-enabled")

    def use_scenario(self, name: str) -> None:
        """Swap in another scenario, so one test can walk a whole matrix."""
        shutil.rmtree(self.scenario_dir, ignore_errors=True)
        shutil.copytree(SCENARIOS / name, self.scenario_dir)

    def _set_env(self, name: str, value: str) -> None:
        previous = os.environ.get(name)
        os.environ[name] = value
        if previous is None:
            self.addCleanup(os.environ.pop, name, None)
        else:
            self.addCleanup(os.environ.__setitem__, name, previous)

    def patch(self, module, name: str, value) -> None:
        original = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, original)

    # -- scenario helpers --------------------------------------------------

    def write_config(self, ssids=None, body: str | None = None):
        path = self.tmp / "urbackup-gated.conf"
        text = (
            body
            if body is not None
            else _CONFIG_TEMPLATE.format(ssids=json.dumps(list(ssids or ALLOWED_SSIDS)))
        )
        path.write_text(text)
        return path

    def load_config(self, ssids=None):
        return config.load(self.write_config(ssids=ssids))

    def set_client_state(self, active: bool = False, enabled: bool = False) -> None:
        for name, wanted in (("client_active", active), ("client_enabled", enabled)):
            marker = self.scenario_dir / name
            if wanted:
                marker.touch()
            else:
                marker.unlink(missing_ok=True)

    def client_is_active(self) -> bool:
        return (self.scenario_dir / "client_active").exists()

    def set_client_status(self, document: dict) -> None:
        (self.scenario_dir / "client_status.json").write_text(json.dumps(document))

    def calls(self, command: str) -> list[str]:
        log = self.scenario_dir / f"{command}-calls.log"
        if not log.exists():
            return []
        return [line for line in log.read_text().splitlines() if line]
