"""Reading the UrBackup client's status and controlling its unit."""

import unittest

import support
from urbackup_gated import client

_RUNNING_PROCESSES = {
    "internet_connected": True,
    "servers": ["urbackup-pi"],
    "running_processes": [
        {
            "action": "INCR",
            "done_bytes": 1073741824,
            "total_bytes": 5368709120,
            "speed_bpms": 1234.5,
        }
    ],
}

_FLAT_SHAPE = {
    "internet_connected": True,
    "action": "FULL",
    "done_bytes": 100,
    "total_bytes": 200,
}


class StatusReading(support.StubbedCase):
    def test_running_backup_from_running_processes(self):
        self.set_client_status(_RUNNING_PROCESSES)
        self.set_client_state(active=True)
        status = client.status()
        self.assertTrue(status.raw_available)
        self.assertTrue(status.unit_active)
        self.assertTrue(status.server_connected)
        self.assertTrue(status.backup_running)
        self.assertEqual(status.action, "INCR")
        self.assertEqual(status.total_bytes, 5368709120)
        self.assertEqual(status.speed_bpms, 1234.5)

    def test_running_backup_from_flat_document(self):
        # The exact shape differs between client versions; both are accepted so
        # a version bump does not silently blank the progress figures.
        self.set_client_status(_FLAT_SHAPE)
        status = client.status()
        self.assertTrue(status.backup_running)
        self.assertEqual(status.action, "FULL")
        self.assertEqual(status.done_bytes, 100)

    def test_idle_client_reports_no_backup(self):
        self.set_client_status({"internet_connected": True, "servers": ["pi"]})
        status = client.status()
        self.assertTrue(status.server_connected)
        self.assertFalse(status.backup_running)
        self.assertIsNone(status.action)

    def test_server_connection_from_servers_list_alone(self):
        self.set_client_status({"internet_connected": False, "servers": ["pi"]})
        self.assertTrue(client.status().server_connected)

    def test_no_server_connection(self):
        self.set_client_status({"internet_connected": False, "servers": []})
        self.assertFalse(client.status().server_connected)

    def test_plain_text_error_is_not_mistaken_for_status(self):
        # This is what the real client prints while its backend is down.
        status = client.status()
        self.assertFalse(status.raw_available)
        self.assertIsNone(status.server_connected)
        self.assertIsNone(status.backup_running)

    def test_nonzero_exit_is_tolerated(self):
        (self.scenario_dir / "client_status.fail").touch()
        self.assertFalse(client.status().raw_available)

    def test_missing_binary_is_tolerated(self):
        self.patch(client, "_CLIENTCTL", str(self.tmp / "no-such-clientctl"))
        self.assertFalse(client.status().raw_available)

    def test_garbage_is_tolerated(self):
        (self.scenario_dir / "client_status.json").write_text("[1, 2, 3]")
        self.assertFalse(client.status().raw_available)


class UnitQueries(support.StubbedCase):
    def test_is_active_follows_the_unit(self):
        self.set_client_state(active=False)
        self.assertFalse(client.is_active())
        self.set_client_state(active=True)
        self.assertTrue(client.is_active())

    def test_is_enabled_follows_the_unit(self):
        self.set_client_state(enabled=False)
        self.assertFalse(client.is_enabled())
        self.set_client_state(enabled=True)
        self.assertTrue(client.is_enabled())


class UnitControl(support.StubbedCase):
    def test_start_and_stop_act_on_the_unit(self):
        client.start()
        self.assertTrue(self.client_is_active())
        client.stop()
        self.assertFalse(self.client_is_active())

    def test_disable_undoes_the_installer(self):
        self.set_client_state(enabled=True)
        client.disable()
        self.assertFalse(client.is_enabled())

    def test_only_the_three_agreed_verbs_reach_systemctl(self):
        client.start()
        client.stop()
        client.disable()
        verbs = {call.split()[0] for call in self.calls("systemctl")}
        self.assertEqual(verbs, {"start", "stop", "disable"})

    def test_the_unit_name_is_never_left_out(self):
        client.start()
        for call in self.calls("systemctl"):
            self.assertTrue(call.endswith(client.UNIT), call)

    def test_failure_raises_instead_of_passing_silently(self):
        self.patch(client, "_SUDO", str(self.tmp / "no-such-sudo"))
        with self.assertRaises(OSError):
            client.start()

    def test_refused_privilege_raises(self):
        refusing = self.tmp / "refusing-sudo"
        refusing.write_text("#!/bin/sh\nexit 1\n")
        refusing.chmod(0o755)
        self.patch(client, "_SUDO", str(refusing))
        with self.assertRaises(client.ControlError):
            client.start()


if __name__ == "__main__":
    unittest.main()
