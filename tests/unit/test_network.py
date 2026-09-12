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
        # The profile is named something else on purpose: a profile can be
        # renamed to anything, including the name of an allowed network.
        connection = network.active_connections()[0]
        self.assertEqual(connection.kind, network.WIFI)
        self.assertEqual(connection.name, "home profile")
        self.assertEqual(connection.ssid, "lieluX")

    def test_the_entry_is_matched_by_device(self):
        network.active_connections()
        wifi_call = next(call for call in self.calls("nmcli") if "wifi" in call)
        self.assertIn("DEVICE", wifi_call)

    def test_scan_is_suppressed(self):
        network.active_connections()
        wifi_call = next(call for call in self.calls("nmcli") if "wifi" in call)
        self.assertIn("--rescan no", wifi_call)


class ColonInSsid(support.StubbedCase):
    scenario = "colon_ssid"

    def test_ssid_with_colons_survives(self):
        self.assertEqual(network.active_connections()[0].ssid, "my:odd:net")


class WifiWithoutAnEntryOfItsOwn(support.StubbedCase):
    """A connected radio the scan list does not mention - an own access point."""

    scenario = "wifi_no_entry"

    def test_the_ssid_stays_unknown(self):
        self.assertIsNone(network.active_connections()[0].ssid)


class TwoWifiDevices(support.StubbedCase):
    """Only one of the two radios has an entry of its own.

    Inferring the SSID from the number of active entries handed that one entry
    to both devices - so a second radio, whose association nobody can see, was
    credited with an allowed network. The DEVICE field settles it outright.
    """

    scenario = "two_wifi_devices"

    def test_each_radio_gets_its_own_entry_and_no_other(self):
        by_device = {c.device: c.ssid for c in network.active_connections()}
        self.assertEqual(by_device, {"wlp0s20f3": "lieluX", "wlan1": None})


class ExternallyConnected(support.StubbedCase):
    """Devices brought up outside NetworkManager report "connected (externally)".

    Comparing the state for equality let them fall through unjudged. Next to an
    ethernet link that reads as "allowed" - exactly the outcome the decision
    rules exist to prevent.
    """

    scenario = "wifi_external"

    def test_an_externally_connected_wifi_is_judged(self):
        kinds = {c.kind for c in network.active_connections()}
        self.assertEqual(kinds, {network.ETHERNET, network.WIFI})

    def test_loopback_stays_out_even_when_externally_connected(self):
        devices = [c.device for c in network.active_connections()]
        self.assertNotIn("lo", devices)


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
