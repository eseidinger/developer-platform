import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from playbook_helpers import load_playbook

ANSIBLE_DIR = Path(__file__).resolve().parents[2]


def mappings(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from mappings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from mappings(nested)


class PlaybookCommandTests(unittest.TestCase):
    def test_postgres_recovery_verifies_fresh_identity_tokens_before_review(self):
        play = load_playbook(
            ANSIBLE_DIR / "tests/platform/test-platform-postgres-outage.yml"
        )[0]
        tasks = list(mappings(play))
        readiness = next(
            row for row in tasks if row.get("register") == "postgres_recovered_readyz"
        )
        authentication = next(
            row
            for row in tasks
            if row.get("register") == "postgres_recovered_runner_token"
        )
        review = next(
            row
            for row in tasks
            if row.get("name")
            == "Resolve the recovery request as platform administrator"
        )
        self.assertLess(tasks.index(readiness), tasks.index(authentication))
        self.assertLess(tasks.index(authentication), tasks.index(review))
        self.assertEqual(
            authentication["ansible.builtin.uri"]["body"]["grant_type"],
            "client_credentials",
        )
        self.assertIn("== 200", authentication["until"])
        self.assertGreater(authentication["retries"], 1)
        self.assertTrue(authentication["no_log"])
        self.assertIn(
            "postgres_recovered_runner_token.json.access_token",
            review["ansible.builtin.uri"]["headers"]["Authorization"],
        )

    def test_scheduled_probe_requires_private_connectivity_and_public_denial(self):
        play = load_playbook(
            ANSIBLE_DIR / "tests/platform/test-platform-components.yml"
        )[0]
        declarations = [
            row["ansible.builtin.uri"]["body"]["spec"]["components"]
            for row in mappings(play)
            if "components"
            in row.get("ansible.builtin.uri", {}).get("body", {}).get("spec", {})
        ]
        probes = 0
        for components in declarations:
            probe = next((row for row in components if row["name"] == "probe"), None)
            if probe is None:
                continue
            probes += 1
            api = next(row for row in components if row["name"] == "api")
            expected_api = 1 if api.get("exposure", "private") == "public" else 0
            command = probe["runtime"]["args"][0]
            # Exercise the real shell assertion with controlled connection
            # outcomes. Merely observing a denied connection is insufficient
            # when its private positive control is also unavailable.
            for peer, public in ((0, 1), (0, 0), (1, 1), (1, 0)):
                expected = 0 if peer == 0 and public == expected_api else 1
                functions = (
                    'wget() { case "$*" in '
                    f"*peer:5678*) return {peer};; "
                    f"*api:5678*) return {public};; "
                    "*) return 99;; esac; }; sleep() { :; }; "
                )
                with self.subTest(peer=peer, public=public):
                    result = subprocess.run(
                        ["sh", "-ec", functions + command],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
                    self.assertEqual(result.returncode, expected)
        self.assertGreaterEqual(probes, 3)

    def test_deliberate_scheduled_failure_finishes_within_poll_deadline(self):
        play = load_playbook(
            ANSIBLE_DIR / "tests/platform/test-platform-components.yml"
        )[0]
        tasks = list(mappings(play))
        wait = next(
            row for row in tasks if row.get("register") == "failing_scheduled_status"
        )
        budget = wait["retries"] * wait["delay"]
        failures = [
            row
            for row in tasks
            if row.get("name") == "failing-probe" and row.get("type") == "scheduled"
        ]
        self.assertGreaterEqual(len(failures), 3)
        for failure in failures:
            self.assertEqual(failure["retryLimit"], 0)
            self.assertLess(60 + failure["maxRunSeconds"], budget)

    def assert_restoration_in_always(self, play):
        scope = next(task for task in play["tasks"] if "always" in task)
        cleanup = scope["always"]
        copies = [task for task in cleanup if "ansible.builtin.copy" in task]
        self.assertEqual(len(copies), 1)
        copy = copies[0]
        self.assertIn("b64decode", copy["ansible.builtin.copy"]["content"])
        self.assertTrue(copy["ansible.builtin.copy"]["dest"].endswith("/.env"))
        commands = [task for task in cleanup if "ansible.builtin.command" in task]
        restore = next(
            task
            for task in commands
            if task["ansible.builtin.command"]["argv"][:3]
            == ["docker", "compose", "up"]
            and task["ansible.builtin.command"]["argv"][-1] == "platform-api"
        )
        self.assertLess(cleanup.index(copy), cleanup.index(restore))
        self.assertFalse(copy["failed_when"])
        self.assertFalse(restore["failed_when"])
        facts = next(
            task["ansible.builtin.set_fact"]
            for task in cleanup
            if "platform_cleanup_restoration_ok"
            in task.get("ansible.builtin.set_fact", {})
        )
        for variable in (copy["register"], restore["register"]):
            self.assertIn(variable, facts["platform_cleanup_restoration_ok"])
        self.assertIn(
            "platform_cleanup_restoration_ok | default(true) | bool",
            cleanup[-1]["ansible.builtin.assert"]["that"],
        )

    def test_all_api_suites_clean_only_registered_creations_in_always(self):
        count = 0
        for path in (ANSIBLE_DIR / "tests/platform").glob("*.yml"):
            play = load_playbook(path)[0]
            scopes = [task for task in play["tasks"] if "always" in task]
            if not scopes:
                continue
            count += 1
            with self.subTest(playbook=path.name):
                scope = scopes[0]
                creation = next(
                    task
                    for task in mappings(scope["block"])
                    if task.get("register") == "platform_cleanup_project_creation"
                )
                self.assertEqual(creation["ansible.builtin.uri"]["method"], "POST")
                self.assertEqual(creation["ansible.builtin.uri"]["status_code"], 201)
                cleanup = scope["always"]
                command = next(
                    task
                    for task in cleanup
                    if task.get("register") == "platform_cleanup_result"
                )
                self.assertTrue(command["no_log"])
                self.assertIn(
                    "platform_cleanup_project_creation",
                    command["ansible.builtin.command"]["stdin"],
                )
                self.assertIn(
                    "platform_cleanup_result.rc == 0",
                    cleanup[-1]["ansible.builtin.assert"]["that"],
                )
        self.assertEqual(count, 8)

    @unittest.skipUnless(shutil.which("ansible-playbook"), "Ansible required")
    def test_real_cleanup_caller_fails_for_unconfirmed_creation_or_restore(self):
        root = ANSIBLE_DIR.parent
        shared = yaml.safe_load(
            (ANSIBLE_DIR / "tasks/tests/support/cleanup.yml").read_text()
        )
        shared[0]["ansible.builtin.command"]["chdir"] = str(root)
        for creation, restored, expected in (
            ({}, True, 0),
            ({"status": 409}, True, 2),
            ({}, False, 2),
        ):
            with (
                self.subTest(creation=creation, restored=restored),
                tempfile.TemporaryDirectory() as directory,
            ):
                play = [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "platform_api_url": "https://unused.invalid",
                            "platform_oidc_token_url": "https://unused.invalid/token",
                            "platform_test_runner_client_id": "unused",
                            "platform_test_runner_client_secret": "must-not-be-disclosed",
                            "platform_cleanup_project_creation": creation,
                            "platform_cleanup_restoration_ok": restored,
                        },
                        "tasks": shared,
                    }
                ]
                file = Path(directory) / "check.yml"
                file.write_text(yaml.safe_dump(play, sort_keys=False))
                environment = {
                    **os.environ,
                    "ANSIBLE_LOCAL_TEMP": directory,
                    "ANSIBLE_NOCOLOR": "1",
                }
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(file)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    result.returncode, expected, result.stdout + result.stderr
                )
                self.assertNotIn("must-not-be-disclosed", result.stdout + result.stderr)

    def test_component_rollback_waits_for_readiness(self):
        play = load_playbook(
            ANSIBLE_DIR / "tests/platform/test-platform-components.yml"
        )
        task = next(
            row
            for row in mappings(play)
            if row.get("register") == "component_rollback_operation"
        )
        self.assertTrue(
            any(
                "readiness.state" in condition and "ready" in condition
                for condition in task["until"]
            )
        )

    def test_egress_negative_connection_precedes_positive_control(self):
        play = load_playbook(
            ANSIBLE_DIR / "tests/platform/test-platform-egress-policy.yml"
        )
        tasks = list(mappings(play))
        negative = next(
            row for row in tasks if row.get("register") == "egress_denied_connection"
        )
        positive = next(
            row for row in tasks if row.get("register") == "egress_deployment"
        )
        self.assertLess(tasks.index(negative), tasks.index(positive))
        self.assertIn("EGRESS_DENIED", negative["failed_when"])
        command = negative["ansible.builtin.command"]["argv"]
        self.assertIn("exec", command)
        self.assertIn("deployment/probe", command)
        self.assertIn("platform_egress_target_host", command[-1])

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
        paths = [ANSIBLE_DIR / "deploy.yml"]
        for directory in ("tasks", "operations", "tests/platform"):
            paths.extend(sorted((ANSIBLE_DIR / directory).rglob("*.yml")))
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
        path = ANSIBLE_DIR / "tests/platform/test-platform-egress-policy.yml"
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
        self.assert_restoration_in_always(load_playbook(path)[0])

    def test_failure_signal_drill_restores_admission_policy(self):
        """The disruptive signal drill must not retain its admission bypass."""
        playbook = load_playbook(
            ANSIBLE_DIR / "tests/platform/test-platform-failure-signals.yml"
        )
        tasks = list(mappings(playbook))
        self.assertTrue(
            any(
                row.get("ansible.builtin.lineinfile", {}).get("line")
                == "CAPACITY_ADMISSION_ENABLED=false"
                for row in tasks
            )
        )
        self.assert_restoration_in_always(playbook[0])

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
        source = (
            ANSIBLE_DIR / "tests/platform/test-platform-hosted-access.yml"
        ).read_text()
        playbook = yaml.safe_load(source)[0]
        self.assertEqual(playbook["vars"]["hosted_access_command"], "plan")
        self.assertFalse(playbook["vars"]["hosted_access_allow_recovery_reconcile"])
        self.assertIn("hosted_access_confirm_environment", source)
        self.assertIn("--operator-token-file", source)
        self.assertNotIn("client_secret", source)
        self.assertNotIn("--volumes", source)
        self.assertTrue(playbook["tasks"][1]["no_log"])

    def test_human_database_access_defaults_to_offline_plan(self):
        source = (
            ANSIBLE_DIR / "tests/platform/test-platform-human-database-access.yml"
        ).read_text()
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
