"""The runtime directory: the manual flag, atomic writes, the status file."""

import json
import os
import unittest

import support
from urbackup_gated import runtime


class ManualFlag(support.StubbedCase):
    def test_absent_file_means_enabled(self):
        # This is what gives "activated at every daemon start" for free.
        self.assertTrue(runtime.read_user_enabled())

    def test_round_trip(self):
        runtime.set_user_enabled(False)
        self.assertFalse(runtime.read_user_enabled())
        runtime.set_user_enabled(True)
        self.assertTrue(runtime.read_user_enabled())

    def test_setting_is_absolute_not_a_toggle(self):
        runtime.set_user_enabled(False)
        runtime.set_user_enabled(False)
        self.assertFalse(runtime.read_user_enabled())

    def test_file_content_is_human_readable(self):
        runtime.set_user_enabled(False)
        self.assertEqual(runtime.USER_ENABLED_FILE.read_text(), "disabled\n")

    def test_hand_written_value_is_accepted(self):
        runtime.USER_ENABLED_FILE.write_text("enabled\n")
        self.assertTrue(runtime.read_user_enabled())

    def test_surrounding_whitespace_is_ignored(self):
        runtime.USER_ENABLED_FILE.write_text("  disabled  \n\n")
        self.assertFalse(runtime.read_user_enabled())

    def test_garbage_is_treated_as_disabled(self):
        # Conservative on purpose: a missed backup is harmless, an unchecked
        # one over a metered link is not.
        runtime.USER_ENABLED_FILE.write_text("maybe\n")
        self.assertFalse(runtime.read_user_enabled())

    def test_empty_file_is_treated_as_disabled(self):
        runtime.USER_ENABLED_FILE.write_text("")
        self.assertFalse(runtime.read_user_enabled())

    def test_clearing_returns_to_enabled(self):
        runtime.set_user_enabled(False)
        runtime.clear_user_enabled()
        self.assertTrue(runtime.read_user_enabled())

    def test_clearing_twice_is_harmless(self):
        runtime.clear_user_enabled()
        runtime.clear_user_enabled()


class AtomicWrites(support.StubbedCase):
    def test_content_is_replaced(self):
        target = self.runtime_dir / "thing"
        runtime.write_atomic(target, "first\n")
        runtime.write_atomic(target, "second\n")
        self.assertEqual(target.read_text(), "second\n")

    def test_no_temporary_file_is_left_behind(self):
        runtime.write_atomic(self.runtime_dir / "thing", "content\n")
        self.assertEqual([p.name for p in self.runtime_dir.iterdir()], ["thing"])

    def test_a_failed_write_leaves_nothing_behind(self):
        def refuse(*_args, **_kwargs):
            raise OSError("no")

        self.patch(os, "replace", refuse)
        with self.assertRaises(OSError):
            runtime.write_atomic(self.runtime_dir / "thing", "content\n")
        self.assertEqual(list(self.runtime_dir.iterdir()), [])


class StatusFile(support.StubbedCase):
    def test_round_trip(self):
        runtime.write_state({"schema_version": 1, "note": "hello"})
        self.assertEqual(runtime.read_state()["note"], "hello")

    def test_written_as_readable_json(self):
        runtime.write_state({"schema_version": 1})
        self.assertEqual(json.loads(runtime.STATE_FILE.read_text())["schema_version"], 1)

    def test_missing_file_reads_as_none(self):
        self.assertIsNone(runtime.read_state())

    def test_corrupt_file_reads_as_none(self):
        runtime.STATE_FILE.write_text("{ not json")
        self.assertIsNone(runtime.read_state())


class DirectoryCheck(support.StubbedCase):
    def test_existing_directory_passes(self):
        runtime.check_directory()

    def test_missing_directory_raises(self):
        self.patch(runtime, "RUNTIME_DIR", self.tmp / "nowhere")
        with self.assertRaises(runtime.RuntimeDirError):
            runtime.check_directory()

    def test_unwritable_directory_raises(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        self.runtime_dir.chmod(0o500)
        self.addCleanup(self.runtime_dir.chmod, 0o755)
        with self.assertRaises(runtime.RuntimeDirError):
            runtime.check_directory()


class WatchedNames(unittest.TestCase):
    def test_state_file_is_not_watched(self):
        # If it were, the daemon's own writes would wake it in a tight loop.
        self.assertNotIn(runtime.STATE_FILE.name, runtime.WATCHED_NAMES)

    def test_both_trigger_files_are_watched(self):
        self.assertEqual(
            runtime.WATCHED_NAMES,
            {runtime.USER_ENABLED_FILE.name, runtime.NETWORK_EVENT_FILE.name},
        )


if __name__ == "__main__":
    unittest.main()
