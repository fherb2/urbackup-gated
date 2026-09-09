"""Configuration loading: accept what is valid, reject everything else.

Rejection matters as much as acceptance here: an invalid configuration must
raise, because the daemon turns that into "keep the client stopped".
"""

import unittest
from pathlib import Path

import support
from urbackup_gated import config


class LoadDefaults(support.StubbedCase):
    def test_shipped_default_config_is_valid(self):
        shipped = support.REPO_ROOT / "packaging/config/urbackup-gated.conf"
        loaded = config.load(shipped)
        self.assertIn("lieluX", loaded.allowed_ssids)
        self.assertIn("lielux", loaded.allowed_ssids)
        self.assertEqual(loaded.check_seconds, 30)
        self.assertEqual(loaded.check_seconds_window_open, 5)
        self.assertEqual(loaded.notify_timeout_seconds, 5)

    def test_ssids_are_case_sensitive(self):
        loaded = config.load(self.write_config(ssids=["lieluX", "lielux"]))
        self.assertEqual(loaded.allowed_ssids, frozenset({"lieluX", "lielux"}))

    def test_only_ssids_are_required(self):
        loaded = config.load(self.write_config(body='allowed_ssids = ["a"]\n'))
        self.assertEqual(loaded.check_seconds, config.DEFAULT_CHECK_SECONDS)
        self.assertEqual(loaded.idle_notify_seconds, config.DEFAULT_IDLE_NOTIFY_SECONDS)
        self.assertEqual(
            loaded.notify_timeout_seconds, config.DEFAULT_NOTIFY_TIMEOUT_SECONDS
        )

    def test_empty_allow_list_is_valid(self):
        loaded = config.load(self.write_config(body="allowed_ssids = []\n"))
        self.assertEqual(loaded.allowed_ssids, frozenset())


class Rejections(support.StubbedCase):
    def test_missing_file(self):
        with self.assertRaises(config.ConfigError):
            config.load(self.tmp / "nowhere.conf")

    def test_unreadable_file(self):
        path = self.write_config()
        path.chmod(0o000)
        self.addCleanup(path.chmod, 0o644)
        if Path("/proc/self").stat().st_uid == 0:
            self.skipTest("root ignores file permissions")
        with self.assertRaises(config.ConfigError):
            config.load(path)

    def test_bad_input_is_rejected(self):
        cases = {
            "broken toml": "allowed_ssids = [",
            "ssids missing": "[intervals]\ncheck_seconds = 30\n",
            "ssids not a list": 'allowed_ssids = "lieluX"\n',
            "ssids not strings": "allowed_ssids = [1, 2]\n",
            "interval zero": 'allowed_ssids = ["a"]\n[intervals]\ncheck_seconds = 0\n',
            "interval negative": 'allowed_ssids = ["a"]\n[intervals]\ncheck_seconds = -5\n',
            "interval not a number": 'allowed_ssids = ["a"]\n[intervals]\ncheck_seconds = "30"\n',
            "interval boolean": 'allowed_ssids = ["a"]\n[intervals]\ncheck_seconds = true\n',
            "intervals not a table": 'allowed_ssids = ["a"]\nintervals = 5\n',
            "notify not a table": 'allowed_ssids = ["a"]\nnotify = "loud"\n',
        }
        for label, body in cases.items():
            with self.subTest(label):
                with self.assertRaises(config.ConfigError):
                    config.load(self.write_config(body=body))

    def test_error_names_the_offending_key(self):
        body = 'allowed_ssids = ["a"]\n[intervals]\nidle_notify_seconds = 0\n'
        with self.assertRaises(config.ConfigError) as raised:
            config.load(self.write_config(body=body))
        self.assertIn("idle_notify_seconds", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
