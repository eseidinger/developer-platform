import unittest
from pathlib import Path

import yaml
from playbook_helpers import load_playbook

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
        tasks = list(mappings(load_playbook(ANSIBLE_DIR / "deploy.yml")))
        names = [task.get("name") for task in tasks]
        validate = names.index(
            "Check shared deployment prerequisites before host maintenance"
        )
        reconcile = names.index("Reconcile Compose services and Kubernetes cluster")
        self.assertLess(validate, reconcile)
        self.assertEqual(
            tasks[validate]["ansible.builtin.command"]["argv"],
            ["python3", "scripts/operations/deploy-platform.py", "--check"],
        )
        self.assertIn(
            "scripts/operations/deploy-platform.py",
            tasks[reconcile]["ansible.builtin.command"]["argv"],
        )
        self.assertTrue(tasks[reconcile]["no_log"])
        # Stop/remove/bootstrap ordering is exercised by the shared command tests.
        self.assertFalse(
            any(
                task.get("ansible.builtin.command", {}).get("argv", [])[:3]
                in (["docker", "compose", "stop"], ["docker", "compose", "rm"])
                for task in tasks
                if isinstance(task.get("ansible.builtin.command"), dict)
            )
        )

    def test_command_argv_never_contains_yaml_null(self):
        """An unquoted standalone dash is YAML null, not kubectl's stdin path."""
        # Include extracted tasks while leaving local inventories and secrets alone.
        paths = sorted(ANSIBLE_DIR.glob("*.yml")) + sorted(
            (ANSIBLE_DIR / "tasks").rglob("*.yml")
        )
        for path in paths:
            if path.name in {"inventory.yml", "human-bootstrap-vars.yml"}:
                continue
            with self.subTest(playbook=path.name):
                documents = yaml.safe_load_all(path.read_text(encoding="utf-8"))
                for document in documents:
                    for mapping in mappings(document):
                        command = mapping.get("ansible.builtin.command")
                        if isinstance(command, dict) and isinstance(
                            command.get("argv"), list
                        ):
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

        tasks = list(mappings(load_playbook(path)))
        self.assertTrue(
            any(
                row.get("key") == "CAPACITY_ADMISSION_ENABLED"
                and row.get("value") == "false"
                for row in tasks
            )
        )
        names = [task.get("name") for task in tasks]
        self.assertIn("Restore the exact original platform environment", names)
        self.assertIn(
            "Recreate only the Platform API with its original egress policy", names
        )

    def test_failure_signal_drill_restores_admission_policy(self):
        """The disruptive signal drill must not retain its admission bypass."""
        playbook = load_playbook(ANSIBLE_DIR / "test-platform-failure-signals.yml")
        tasks = list(mappings(playbook))
        self.assertTrue(
            any(
                row.get("ansible.builtin.lineinfile", {}).get("line")
                == "CAPACITY_ADMISSION_ENABLED=false"
                for row in tasks
            )
        )
        names = [task.get("name") for task in tasks]
        self.assertIn("Restore the exact original platform environment", names)
        self.assertIn(
            "Recreate only the Platform API with its original failure-drill policy",
            names,
        )

    def test_inventory_egress_settings_are_rendered_into_platform_environment(self):
        deploy = yaml.safe_load(
            (ANSIBLE_DIR / "deploy.yml").read_text(encoding="utf-8")
        )
        settings = deploy[0]["vars"]["platform_settings"]
        self.assertEqual(
            settings["ALLOWED_EGRESS_CIDRS"], "{{ platform_allowed_egress_cidrs }}"
        )
        self.assertEqual(
            settings["ALLOWED_EGRESS_PORTS"], "{{ platform_allowed_egress_ports }}"
        )
        example = yaml.safe_load(
            (ANSIBLE_DIR / "inventory.example.yml").read_text(encoding="utf-8")
        )
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
