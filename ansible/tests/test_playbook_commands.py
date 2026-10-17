import unittest
from pathlib import Path

import yaml


ANSIBLE_DIR = Path(__file__).resolve().parents[1]


def mappings(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from mappings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from mappings(nested)


class PlaybookCommandTests(unittest.TestCase):
    def test_network_settings_are_validated_before_deployment_outage(self):
        source = (ANSIBLE_DIR / "deploy.yml").read_text()
        validate = source.index("Validate fixed Docker addresses before stopping services")
        stop = source.index("Stop existing Compose services cleanly")
        reconcile = source.index("Reconcile Compose services and Kubernetes cluster")
        self.assertLess(validate, stop)
        self.assertLess(stop, reconcile)
        self.assertIn("--validate-networks", source[validate:stop])

    def test_command_argv_never_contains_yaml_null(self):
        """An unquoted standalone dash is YAML null, not kubectl's stdin path."""
        for path in sorted(ANSIBLE_DIR.glob("*.yml")):
            with self.subTest(playbook=path.name):
                documents = yaml.safe_load_all(path.read_text(encoding="utf-8"))
                for document in documents:
                    for mapping in mappings(document):
                        command = mapping.get("ansible.builtin.command")
                        if isinstance(command, dict) and isinstance(command.get("argv"), list):
                            self.assertNotIn(None, command["argv"])

    def test_egress_drill_has_safe_overridable_defaults_and_restores_policy(self):
        """The protected egress drill must not leave its temporary allow-list behind."""
        path = ANSIBLE_DIR / "test-platform-egress-policy.yml"
        playbook = yaml.safe_load(path.read_text(encoding="utf-8"))
        variables = playbook[0]["vars"]

        self.assertEqual("1.1.1.1", variables["platform_egress_target_host"])
        self.assertEqual("1.1.1.1/32", variables["platform_egress_target_cidr"])
        self.assertEqual(853, variables["platform_egress_target_port"])
        self.assertIn("@sha256:", variables["platform_egress_drill_image"])

        source = path.read_text(encoding="utf-8")
        self.assertIn("CAPACITY_ADMISSION_ENABLED, value: 'false'", source)
        self.assertIn("Restore the exact original platform environment", source)
        self.assertIn("Recreate only the Platform API with its original egress policy", source)

    def test_failure_signal_drill_restores_admission_policy(self):
        """The disruptive signal drill must not retain its admission bypass."""
        source = (ANSIBLE_DIR / "test-platform-failure-signals.yml").read_text(encoding="utf-8")
        self.assertIn("CAPACITY_ADMISSION_ENABLED=false", source)
        self.assertIn("Restore the exact original platform environment", source)
        self.assertIn("Recreate only the Platform API with its original failure-drill policy", source)

    def test_inventory_egress_settings_are_rendered_into_platform_environment(self):
        deploy = yaml.safe_load((ANSIBLE_DIR / "deploy.yml").read_text(encoding="utf-8"))
        settings = deploy[0]["vars"]["platform_settings"]
        self.assertEqual(settings["ALLOWED_EGRESS_CIDRS"], "{{ platform_allowed_egress_cidrs }}")
        self.assertEqual(settings["ALLOWED_EGRESS_PORTS"], "{{ platform_allowed_egress_ports }}")
        example = yaml.safe_load((ANSIBLE_DIR / "inventory.example.yml").read_text(encoding="utf-8"))
        variables = example["all"]["children"]["developer_platform"]["vars"]
        self.assertEqual(variables["platform_allowed_egress_cidrs"], "")
        self.assertEqual(variables["platform_allowed_egress_ports"], "")

    def test_hosted_access_defaults_to_plan_and_passes_no_secret_values(self):
        source = (ANSIBLE_DIR / "test-platform-hosted-access.yml").read_text()
        playbook = yaml.safe_load(source)[0]
        self.assertEqual(playbook["vars"]["hosted_access_command"], "plan")
        self.assertFalse(playbook["vars"]["hosted_access_allow_recovery_reconcile"])
        self.assertIn("hosted_access_confirm_environment", source)
        self.assertIn("--operator-token-file", source)
        self.assertNotIn("client_secret", source)
        self.assertNotIn("--volumes", source)
        self.assertTrue(playbook["tasks"][1]["no_log"])

    def test_human_database_access_defaults_to_offline_plan(self):
        source = (ANSIBLE_DIR / "test-platform-human-database-access.yml").read_text()
        playbook = yaml.safe_load(source)[0]
        self.assertEqual(playbook["vars"]["human_database_command"], "plan")
        self.assertIn("human_database_confirm_environment", source)
        self.assertIn("--operator-token-file", source)
        self.assertIn("--known-hosts-file", source)
        self.assertNotIn("client_secret", source)
        self.assertNotIn("--volumes", source)
        self.assertTrue(playbook["tasks"][1]["no_log"])


if __name__ == "__main__":
    unittest.main()
