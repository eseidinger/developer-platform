"""Offline public-spec and assertion contract for the named-store rollback playbook."""

import json
import sys
import unittest
from pathlib import Path

from playbook_helpers import load_playbook

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/app/src"))
from app.spec import ApplicationEnvelopeV1Alpha2, to_flat

PLAYBOOK = load_playbook(
    ROOT / "ansible/tests/platform/test-platform-rollback-data.yml"
)[0]
DRILL = next(
    row
    for row in PLAYBOOK["tasks"]
    if row["name"] == "Exercise data-aware rollback on a disposable project"
)
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
    def test_both_declarations_are_valid_and_keep_same_named_binding(self):
        specs = []
        for name in (
            "Deploy the first application revision",
            "Deploy a second application revision",
        ):
            body = render(task(name)["ansible.builtin.uri"]["body"])
            ApplicationEnvelopeV1Alpha2.model_validate(body)
            specs.append(to_flat(body))
        self.assertEqual(
            [spec["name"] for spec in specs], ["rollback-0123456789ab"] * 2
        )
        components = [spec["components"][0] for spec in specs]
        self.assertEqual(
            [item["bindings"][0]["bindingId"] for item in components], [BINDING] * 2
        )
        self.assertEqual([item["name"] for item in components], ["web", "web"])
        self.assertEqual(
            [item["resources"]["limits"]["cpu"] for item in components],
            ["500m", "600m"],
        )
        self.assertEqual(
            [spec["configuration"]["ACCEPTANCE_RUN_ID"] for spec in specs],
            ["0123456789ab"] * 2,
        )

    def test_resource_and_binding_are_ready_before_deployment(self):
        names = [row["name"] for row in TASKS]
        self.assertLess(
            names.index("Wait for the named PostgreSQL resource"),
            names.index("Bind the named resource to the web component"),
        )
        self.assertLess(
            names.index("Wait for the web component binding"),
            names.index("Deploy the first application revision"),
        )
        self.assertLess(
            names.index("Roll back the application to revision one"),
            names.index(
                "Require the named database visit to survive application rollback"
            ),
        )
        self.assertLess(
            names.index(
                "Require the named database visit to survive application rollback"
            ),
            names.index("Require the same binding to remain active after rollback"),
        )
        for name in (
            "Write the first database-backed visit through the bound workload",
            "Require the named database visit to survive application rollback",
        ):
            command = task(name)["ansible.builtin.command"]["argv"]
            self.assertIn("deployment/web", command)
            self.assertNotIn("psql", command)

    def test_cleanup_requires_confirmed_project_creation(self):
        self.assertNotIn(
            "platform_rollback_project",
            PLAYBOOK["tasks"][1]["ansible.builtin.set_fact"]["rollback_project"],
        )
        creation = task("Create the disposable rollback project")
        self.assertEqual(creation["register"], "platform_cleanup_project_creation")
        cleanup = next(
            row for row in CLEANUP if row.get("register") == "platform_cleanup_result"
        )
        self.assertIn(
            "platform_cleanup_project_creation",
            cleanup["ansible.builtin.command"]["stdin"],
        )
        self.assertEqual(
            CLEANUP[-1]["ansible.builtin.assert"]["that"][0],
            "platform_cleanup_result.rc == 0",
        )
        secret_check = task(
            "Verify the current secret is injected after rollback without disclosing it"
        )
        command = secret_check["ansible.builtin.command"]["argv"]
        self.assertTrue(secret_check["no_log"])
        self.assertNotIn("current-{{ rollback_run_id }}", command)


if __name__ == "__main__":
    unittest.main()
