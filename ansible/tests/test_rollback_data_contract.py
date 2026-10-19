"""Offline public-spec and assertion contract for the named-store rollback playbook."""
import json
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/app/src"))
try:
    from app.spec import ApplicationEnvelopeV1Alpha2, to_flat
except ModuleNotFoundError:  # Ansible's controller Python omits app/Kubernetes dependencies.
    ApplicationEnvelopeV1Alpha2 = None
    to_flat = None

PLAYBOOK = yaml.safe_load((ROOT / "ansible/test-platform-rollback-data.yml").read_text())[0]
DRILL = next(row for row in PLAYBOOK["tasks"]
             if row["name"] == "Exercise data-aware rollback on a disposable project")
TASKS = DRILL["block"]
CLEANUP = DRILL["always"]
IMAGE = "docker.io/example/web-postgres@sha256:" + "a" * 64
BINDING = "11111111-1111-1111-1111-111111111111"


def task(name):
    return next(row for row in TASKS if row["name"] == name)


def render(body):
    value = json.dumps(body)
    for variable, replacement in (
        ("rollback_project", "rollback-0123456789ab"),
        ("platform_rollback_drill_image", IMAGE),
        ("rollback_binding_request.json.grant_id", BINDING),
        ("rollback_run_id", "0123456789ab"),
    ):
        value = value.replace("{{ " + variable + " }}", replacement)
    return json.loads(value)


class RollbackDataContractTests(unittest.TestCase):
    @unittest.skipIf(ApplicationEnvelopeV1Alpha2 is None, "application schema dependencies unavailable")
    def test_both_declarations_are_valid_and_keep_same_named_binding(self):
        specs = []
        for name in ("Deploy the first application revision", "Deploy a second application revision"):
            body = render(task(name)["ansible.builtin.uri"]["body"])
            ApplicationEnvelopeV1Alpha2.model_validate(body)
            specs.append(to_flat(body))
        self.assertEqual([spec["name"] for spec in specs], ["rollback-0123456789ab"] * 2)
        components = [spec["components"][0] for spec in specs]
        self.assertEqual([item["bindings"][0]["bindingId"] for item in components], [BINDING] * 2)
        self.assertEqual([item["name"] for item in components], ["web", "web"])
        self.assertEqual([item["resources"]["limits"]["cpu"] for item in components], ["500m", "600m"])
        self.assertEqual([spec["configuration"]["ACCEPTANCE_RUN_ID"] for spec in specs], ["0123456789ab"] * 2)

    def test_resource_and_binding_are_ready_before_deployment(self):
        names = [row["name"] for row in TASKS]
        self.assertLess(names.index("Wait for the named PostgreSQL resource"),
                        names.index("Bind the named resource to the web component"))
        self.assertLess(names.index("Wait for the web component binding"),
                        names.index("Deploy the first application revision"))
        self.assertLess(names.index("Roll back the application to revision one"),
                        names.index("Require the named database visit to survive application rollback"))
        self.assertLess(names.index("Require the named database visit to survive application rollback"),
                        names.index("Require the same binding to remain active after rollback"))
        for name in ("Write the first database-backed visit through the bound workload",
                     "Require the named database visit to survive application rollback"):
            command = task(name)["ansible.builtin.command"]["argv"]
            self.assertIn("deployment/web", command)
            self.assertNotIn("psql", command)

    def test_cleanup_requires_confirmed_project_creation(self):
        names = [row["name"] for row in TASKS]
        self.assertEqual(names[names.index("Create the disposable rollback project") + 1],
                         "Record confirmed ownership of the disposable project")
        self.assertNotIn("platform_rollback_project", PLAYBOOK["tasks"][1]["ansible.builtin.set_fact"]["rollback_project"])
        for row in CLEANUP:
            if row["name"] in ("Read rollback-project retirement scope", "Retire the disposable rollback project"):
                self.assertIn("rollback_project_created | default(false)", row["when"])
        secret_check = task("Verify the current secret is injected after rollback without disclosing it")
        command = secret_check["ansible.builtin.command"]["argv"]
        self.assertTrue(secret_check["no_log"])
        self.assertNotIn("current-{{ rollback_run_id }}", command)


if __name__ == "__main__":
    unittest.main()
