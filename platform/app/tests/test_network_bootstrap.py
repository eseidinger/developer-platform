import importlib.util
import ipaddress
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("network_addresses", ROOT / "scripts/checks/check-network-addresses.py")
network_addresses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network_addresses)


class NetworkBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.subnet, self.fixed = network_addresses.addresses({})
        self.network = {
            "IPAM": {"Config": [{"Subnet": "172.30.80.0/24", "Gateway": "172.30.80.1"}]},
            "Containers": {},
        }

    def test_defaults_and_custom_addresses(self):
        self.assertEqual(str(self.fixed["platform-api"]), "172.30.80.11")
        self.assertEqual(str(self.fixed["keycloak"]), "172.30.80.12")
        custom = {key: "192.0.2." + default.rsplit(".", 1)[1]
                  for key, default in network_addresses.FIXED_SERVICES.values()}
        subnet, fixed = network_addresses.addresses({"PLATFORM_SUBNET": "192.0.2.0/24", **custom})
        self.assertEqual(subnet, ipaddress.IPv4Network("192.0.2.0/24"))
        self.assertEqual(str(fixed["postgres"]), "192.0.2.10")
        self.assertEqual(str(fixed["alertmanager"]), "192.0.2.26")

    def test_invalid_addresses_fail_without_echoing_values(self):
        for config in ({"KEYCLOAK_IP": "secret-value"}, {"PLATFORM_SUBNET": "secret-value"},
                       {"KEYCLOAK_IP": "172.30.80.11"}, {"KEYCLOAK_IP": "172.30.81.12"},
                       {"KEYCLOAK_IP": "172.30.80.0"}, {"KEYCLOAK_IP": "172.30.80.255"}):
            with self.subTest(config=config), self.assertRaises(ValueError) as error:
                network_addresses.addresses(config)
            self.assertNotIn("secret-value", str(error.exception))

    def test_validation_only_never_contacts_docker(self):
        with patch.object(network_addresses, "settings", return_value={}), \
                patch.object(sys, "argv", ["check-network-addresses.py", "--validate-only"]), \
                patch.object(network_addresses, "docker") as docker, redirect_stdout(io.StringIO()):
            network_addresses.check()
        docker.assert_not_called()

    def test_pre_outage_validation_allows_recreatable_container_address_conflicts(self):
        self.network['Containers'] = {'fixture': {'IPv4Address': '172.30.80.11/24', 'Name': 'compose-peer'}}
        with patch.object(network_addresses, 'settings', return_value={}), \
                patch.object(sys, 'argv', ['check-network-addresses.py', '--validate-networks']), \
                patch.object(network_addresses, 'docker', side_effect=['developer-platform', json.dumps([self.network])]) as docker, \
                redirect_stdout(io.StringIO()):
            network_addresses.check()
        self.assertEqual(docker.call_count, 2)

    def test_pre_outage_validation_refuses_existing_network_subnet_change(self):
        self.network['IPAM']['Config'][0]['Subnet'] = '10.55.8.0/24'
        with patch.object(network_addresses, 'settings', return_value={}), \
                patch.object(sys, 'argv', ['check-network-addresses.py', '--validate-networks']), \
                patch.object(network_addresses, 'docker', side_effect=['developer-platform', json.dumps([self.network])]), \
                self.assertRaisesRegex(ValueError, 'separate migration'):
            network_addresses.check()

    def test_search_console_network_is_separate_and_has_fixed_non_gateway_members(self):
        subnet, fixed = network_addresses.console_addresses({})
        self.assertFalse(subnet.overlaps(self.subnet))
        self.assertEqual(str(fixed['opensearch-dashboards']), '172.30.81.3')
        for config in ({'STORE_SEARCH_API_IP': '172.30.81.3'}, {'OPENSEARCH_DASHBOARDS_IP': '172.30.81.1'},
                {'OPENSEARCH_DASHBOARDS_IP': '172.30.80.31'}, {'STORE_SEARCH_CONSOLE_SUBNET': 'private-value'},
                {'STORE_SEARCH_CONSOLE_SUBNET': '172.30.80.0/24', 'STORE_SEARCH_API_IP': '172.30.80.2',
                    'OPENSEARCH_DASHBOARDS_IP': '172.30.80.3'}):
            with self.assertRaises(ValueError) as denied:
                network_addresses.addresses(config)
            self.assertNotIn('private-value', str(denied.exception))

    def test_daemon_failure_never_forwards_arbitrary_diagnostics(self):
        with patch.object(network_addresses.subprocess, "run", return_value=Mock(
                returncode=1, stdout="", stderr="private-secret-value")):
            with self.assertRaises(ValueError) as error:
                network_addresses.docker("network", "inspect", "developer-platform")
        self.assertNotIn("private-secret-value", str(error.exception))

    def test_empty_network_and_intended_owners_are_accepted(self):
        self.assertEqual(network_addresses.conflicts(self.subnet, self.fixed, self.network, None), [])
        self.network["Containers"] = {
            name: {"IPv4Address": str(address) + "/24", "Name": "developer-platform-" + name + "-1"}
            for name, address in self.fixed.items()
        }
        labels = lambda name: {"com.docker.compose.project": "developer-platform", "com.docker.compose.service": name}
        self.assertEqual(network_addresses.conflicts(self.subnet, self.fixed, self.network, labels), [])

    def test_reports_both_observed_conflicts(self):
        self.network["Containers"] = {
            "loki": {"IPv4Address": "172.30.80.11/24", "Name": "developer-platform-loki-1"},
            "proxy": {"IPv4Address": "172.30.80.12/24", "Name": "developer-platform-proxy-1"},
        }
        labels = lambda name: {"com.docker.compose.project": "developer-platform", "com.docker.compose.service": name}
        errors = network_addresses.conflicts(self.subnet, self.fixed, self.network, labels)
        self.assertEqual(len(errors), 2)
        self.assertIn("platform-api: 172.30.80.11 is occupied by developer-platform-loki-1", errors)
        self.assertIn("keycloak: 172.30.80.12 is occupied by developer-platform-proxy-1", errors)

    def test_monitoring_container_cannot_occupy_gateway_address(self):
        self.network["Containers"] = {
            "alertmanager": {"IPv4Address": "172.30.80.13/24", "Name": "developer-platform-alertmanager-1"},
        }
        errors = network_addresses.conflicts(self.subnet, self.fixed, self.network,
                                            lambda _: {"com.docker.compose.project": "developer-platform",
                                                       "com.docker.compose.service": "alertmanager"})
        self.assertEqual(errors, ["telemetry-gateway: 172.30.80.13 is occupied by developer-platform-alertmanager-1"])

    def test_foreign_owner_and_gateway_are_rejected(self):
        self.network["Containers"] = {"foreign": {"IPv4Address": "172.30.80.12/24", "Name": "foreign"}}
        errors = network_addresses.conflicts(self.subnet, self.fixed, self.network,
                                            lambda _: {"com.docker.compose.service": "keycloak"})
        self.assertEqual(len(errors), 1)
        self.fixed["postgres"] = ipaddress.IPv4Address("172.30.80.1")
        errors = network_addresses.conflicts(self.subnet, self.fixed, self.network, lambda _: {})
        self.assertTrue(any("network gateway" in error for error in errors))

    def test_subnet_change_requires_operator_review(self):
        self.network["IPAM"]["Config"][0]["Subnet"] = "192.0.2.0/24"
        with self.assertRaisesRegex(ValueError, "do not remove the network"):
            network_addresses.conflicts(self.subnet, self.fixed, self.network, None)

    def test_fixed_core_starts_before_dynamic_services(self):
        source = (ROOT / "scripts/up.sh").read_text()
        postgres = source.index("docker compose up -d --wait --wait-timeout 120 postgres")
        cluster = source.index("k3d cluster create")
        core = source.index("docker compose up -d --build --wait --wait-timeout 180 platform-api")
        remaining = source.index("docker compose up -d --build --remove-orphans")
        self.assertLess(postgres, cluster)
        self.assertLess(cluster, core)
        self.assertLess(core, remaining)
        self.assertIn("check-network-addresses.py", source[cluster:core])
        self.assertIn("check-network-addresses.py", source[core:remaining])
        self.assertNotIn("docker compose down", source)


if __name__ == "__main__":
    unittest.main()
