"""nmcli output parsing and the command line we build for it."""

import unittest

import support
from urbackup_gated import network


class TerseSplitting(unittest.TestCase):
    """nmcli -t escapes ':' and '\\'; a naive split would tear values apart."""

    def test_plain_fields(self):
        self.assertEqual(
            network._split_terse("wlp0s20f3:wifi:connected:home"),
            ["wlp0s20f3", "wifi", "connected", "home"],
        )

    def test_escaped_colon_stays_in_the_value(self):
        self.assertEqual(
            network._split_terse(r"yes:my\:odd\:net"), ["yes", "my:odd:net"]
        )

    def test_escaped_backslash(self):
        self.assertEqual(network._split_terse(r"yes:back\\slash"), ["yes", "back\\slash"])

    def test_trailing_empty_field_is_kept(self):
        self.assertEqual(
            network._split_terse("wlp0s20f3:wifi:disconnected:"),
            ["wlp0s20f3", "wifi", "disconnected", ""],
        )


class ActiveConnections(support.StubbedCase):
    scenario = "ethernet_only"

    def test_only_connected_devices_and_no_loopback(self):
        connections = network.active_connections()
        self.assertEqual([c.device for c in connections], ["enp0s31f6"])
        self.assertEqual(connections[0].kind, network.ETHERNET)
        self.assertIsNone(connections[0].ssid)

    def test_query_is_locale_independent_and_terse(self):
        network.active_connections()
        status_call = self.calls("nmcli")[0]
        self.assertIn("-t", status_call)
        self.assertIn("LC_ALL=C", status_call)

    def test_wifi_list_is_not_queried_without_a_wifi_connection(self):
        network.active_connections()
        self.assertEqual(len(self.calls("nmcli")), 1)


class WifiConnections(support.StubbedCase):
    scenario = "allowed_wifi"

    def test_ssid_comes_from_the_radio_not_the_profile_name(self):
        connection = network.active_connections()[0]
        self.assertEqual(connection.kind, network.WIFI)
        self.assertEqual(connection.name, "home profile")
        self.assertEqual(connection.ssid, "lieluX")

    def test_scan_is_suppressed(self):
        network.active_connections()
        wifi_call = next(call for call in self.calls("nmcli") if "wifi" in call)
        self.assertIn("--rescan no", wifi_call)


class ColonInSsid(support.StubbedCase):
    scenario = "colon_ssid"

    def test_ssid_with_colons_survives(self):
        self.assertEqual(network.active_connections()[0].ssid, "my:odd:net")


class AmbiguousWifi(support.StubbedCase):
    scenario = "wifi_name_mismatch"

    def test_unresolvable_ssid_stays_unknown(self):
        # Two active SSIDs and a profile name matching neither: guessing here
        # would be the one mistake that lets a metered network pass.
        self.assertIsNone(network.active_connections()[0].ssid)


class NothingConnected(support.StubbedCase):
    scenario = "nothing"

    def test_no_connections(self):
        self.assertEqual(network.active_connections(), ())


class Failures(support.StubbedCase):
    scenario = "nmcli_error"

    def test_failing_nmcli_raises(self):
        with self.assertRaises(network.NetworkQueryError):
            network.active_connections()

    def test_missing_nmcli_raises(self):
        self.patch(network, "_NMCLI", str(self.tmp / "no-such-nmcli"))
        with self.assertRaises(network.NetworkQueryError):
            network.active_connections()


if __name__ == "__main__":
    unittest.main()
