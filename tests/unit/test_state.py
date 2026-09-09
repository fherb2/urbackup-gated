"""The decision itself, and the wording that explains it.

This is the heart of the service: the rule that a single forbidden wifi forbids
backups even next to an unmetered ethernet connection, combined with the manual
flag by logical AND.
"""

import unittest
from datetime import datetime

import support
from urbackup_gated import runtime, state

# scenario, expected network verdict, expected effective verdict while the user
# has not objected, and a fragment of the reason the user gets to read.
MATRIX = [
    ("ethernet_only", True, True, "allowed connection active"),
    ("allowed_wifi", True, True, "allowed connection active"),
    ("forbidden_wifi", False, False, "not on the allow list"),
    ("ethernet_and_forbidden_wifi", False, False, "not on the allow list"),
    ("colon_ssid", False, False, "my:odd:net"),
    ("wifi_name_mismatch", False, False, "not on the allow list"),
    ("nothing", None, None, "no network connection"),
    ("nmcli_error", False, False, "network state unknown"),
]


class DecisionMatrix(support.StubbedCase):
    def test_network_verdict_and_reason(self):
        for scenario, allows, effective, reason in MATRIX:
            with self.subTest(scenario):
                self.use_scenario(scenario)
                decision = state.gather(self.load_config())["decision"]
                self.assertIs(decision["network_allows"], allows)
                self.assertIs(decision["effective"], effective)
                self.assertIn(reason, decision["reason"])

    def test_ethernet_does_not_rescue_a_forbidden_wifi(self):
        # The docking station case, spelled out: this is the whole point of
        # judging every connection instead of only the primary one.
        self.use_scenario("ethernet_and_forbidden_wifi")
        status = state.gather(self.load_config())
        kinds = {c["kind"] for c in status["network"]["connections"]}
        self.assertEqual(kinds, {"ethernet", "wifi"})
        self.assertFalse(status["decision"]["effective"])

    def test_manual_objection_wins_everywhere(self):
        runtime.set_user_enabled(False)
        for scenario, _allows, _effective, _reason in MATRIX:
            with self.subTest(scenario):
                self.use_scenario(scenario)
                decision = state.gather(self.load_config())["decision"]
                self.assertFalse(decision["user_enabled"])
                self.assertIs(decision["effective"], False)
                self.assertEqual(decision["reason"], "manually deactivated")

    def test_withdrawing_the_objection_does_not_override_the_network(self):
        self.use_scenario("forbidden_wifi")
        runtime.set_user_enabled(True)
        decision = state.gather(self.load_config())["decision"]
        self.assertTrue(decision["user_enabled"])
        self.assertFalse(decision["effective"])

    def test_allow_list_is_case_sensitive(self):
        self.use_scenario("allowed_wifi")
        decision = state.gather(self.load_config(ssids=["lielux"]))["decision"]
        self.assertFalse(decision["effective"])


class Document(support.StubbedCase):
    scenario = "allowed_wifi"

    def test_schema_version_and_timestamp(self):
        status = state.gather(self.load_config())
        self.assertEqual(status["schema_version"], state.SCHEMA_VERSION)
        written = datetime.fromisoformat(status["written_at"])
        self.assertIsNotNone(written.tzinfo)

    def test_connection_entries_carry_the_verdict(self):
        entry = state.gather(self.load_config())["network"]["connections"][0]
        self.assertEqual(entry["ssid"], "lieluX")
        self.assertIs(entry["allowed"], True)

    def test_ethernet_entries_have_no_verdict_of_their_own(self):
        self.use_scenario("ethernet_only")
        entry = state.gather(self.load_config())["network"]["connections"][0]
        self.assertIsNone(entry["allowed"])

    def test_client_section_is_present_without_a_backend(self):
        client_view = state.gather(self.load_config())["urbackup_client"]
        self.assertFalse(client_view["raw_available"])
        self.assertIn("unit_active", client_view)


class Rendering(support.StubbedCase):
    def test_every_scenario_renders_without_crashing(self):
        for scenario, _allows, _effective, reason in MATRIX:
            with self.subTest(scenario):
                self.use_scenario(scenario)
                text = state.format_status(state.gather(self.load_config()))
                self.assertIn(reason, text)
                self.assertIn("urbackup-gated", text)

    def test_labels_are_aligned(self):
        self.use_scenario("ethernet_only")
        text = state.format_status(state.gather(self.load_config()))
        values = [
            line.index(word)
            for line in text.splitlines()
            for word in ("yes", "no", "unknown")
            if line.startswith("  ") and line.rstrip().endswith(word)
        ]
        self.assertTrue(values)
        self.assertEqual(len(set(values)), 1, text)

    def test_progress_is_shown_while_a_backup_runs(self):
        self.use_scenario("ethernet_only")
        self.set_client_status(
            {
                "internet_connected": True,
                "running_processes": [
                    {
                        "action": "INCR",
                        "done_bytes": 1073741824,
                        "total_bytes": 5368709120,
                        "speed_bpms": 2000,
                    }
                ],
            }
        )
        text = state.format_status(state.gather(self.load_config()))
        self.assertIn("1024 of 5120 MiB (20.0 %)", text)
        self.assertIn("2.00 MB/s", text)

    def test_progress_is_omitted_without_a_total(self):
        self.use_scenario("ethernet_only")
        self.set_client_status(
            {"internet_connected": True, "running_processes": [{"action": "INCR"}]}
        )
        text = state.format_status(state.gather(self.load_config()))
        self.assertIn("INCR", text)
        self.assertNotIn("progress:", text)


class NotificationText(support.StubbedCase):
    scenario = "ethernet_only"

    def test_running_backup_reports_progress(self):
        self.set_client_status(
            {
                "internet_connected": True,
                "running_processes": [
                    {"action": "INCR", "done_bytes": 50, "total_bytes": 100}
                ],
            }
        )
        summary, body = state.notify_summary(state.gather(self.load_config()))
        self.assertIn("INCR", summary)
        self.assertIn("50.0 %", body)

    def test_blocked_state_reports_the_reason(self):
        self.use_scenario("forbidden_wifi")
        status = state.gather(self.load_config())
        summary, body = state.notify_summary(status)
        self.assertIn("not backing up", summary)
        self.assertEqual(body, status["decision"]["reason"])

    def test_manual_objection_is_named_in_the_notification(self):
        runtime.set_user_enabled(False)
        _summary, body = state.notify_summary(state.gather(self.load_config()))
        self.assertEqual(body, "manually deactivated")


if __name__ == "__main__":
    unittest.main()
