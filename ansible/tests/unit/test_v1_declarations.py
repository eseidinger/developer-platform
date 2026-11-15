"""Deployment playbooks must send the sole public v1 Application envelope."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def declarations(value):
    if isinstance(value, dict):
        request = value.get("ansible.builtin.uri", {})
        if request.get("method") == "PUT" and str(request.get("url", "")).endswith(
            "/application"
        ):
            yield request
        for child in value.values():
            yield from declarations(child)
    elif isinstance(value, list):
        for child in value:
            yield from declarations(child)


class DeclarationTests(unittest.TestCase):
    def test_every_deployment_uses_the_v1_component_envelope(self):
        total = 0
        paths = [
            path
            for directory in ("operations", "tasks/tests", "tests/platform")
            for path in (ROOT / "ansible" / directory).rglob("*.yml")
        ]
        for path in paths:
            for request in declarations(yaml.safe_load(path.read_text())):
                body = request.get("body")
                if not isinstance(body, dict):
                    continue
                total += 1
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertEqual(
                        body.get("apiVersion"), "platform.eseidinger.de/v1"
                    )
                    self.assertEqual(body.get("kind"), "Application")
                    self.assertEqual(set(body.get("metadata", {})), {"name"})
                    self.assertIn("components", body["spec"])
        self.assertGreater(total, 10)

    def test_full_component_updates_preserve_the_explicit_acceptance_configuration(
        self,
    ):
        for name in ("rollout.yml", "service-update.yml", "scheduled-update.yml"):
            path = ROOT / "ansible/tasks/tests/components" / name
            for request in declarations(yaml.safe_load(path.read_text())):
                with self.subTest(name=name):
                    self.assertEqual(
                        request["body"]["spec"]["configuration"]["values"],
                        {"COMPONENT_ACCEPTANCE_RUN": "{{ component_run_id }}"},
                    )
