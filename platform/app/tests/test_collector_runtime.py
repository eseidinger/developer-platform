import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("workload_log_fixture", ROOT / "scripts/check-workload-logs.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class CollectorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.service = yaml.safe_load(
            (ROOT / "infrastructure/monitoring/compose.yaml").read_text()
        )["services"]["alloy"]

    def test_image_state_group_without_relaxing_hardening(self):
        self.assertEqual(self.service["image"], fixture.ALLOY)
        self.assertEqual(self.service["user"], "0:473")
        self.assertTrue(self.service["read_only"])
        self.assertEqual(self.service["cap_drop"], ["ALL"])
        self.assertNotIn("cap_add", self.service)
        self.assertNotIn("privileged", self.service)
        self.assertEqual(self.service["security_opt"], ["no-new-privileges:true"])
        self.assertNotIn("ports", self.service)
        self.assertIn("alloy:/var/lib/alloy", self.service["volumes"])
        self.assertIn("--storage.path=/var/lib/alloy", self.service["command"])

    def test_fixture_uses_production_volume_identity_and_healthcheck(self):
        args = fixture.collector_runtime(self.service, "disposable-test-state")
        self.assertEqual(args[args.index("--user") + 1], "0:473")
        self.assertIn("disposable-test-state:/var/lib/alloy", args)
        self.assertIn("--read-only", args)
        self.assertEqual(args[args.index("--cap-drop") + 1], "ALL")
        health = args[args.index("--health-cmd") + 1]
        self.assertIn("/-/ready", health)
        self.assertIn("$status", health)
        self.assertNotIn("$$status", health)
        self.assertNotIn("curl", health)
        self.assertNotIn("wget", health)

    def test_bootstrap_requires_collector_health_before_success(self):
        source = (ROOT / "scripts/up.sh").read_text()
        start = source.index("docker compose up -d --build --remove-orphans")
        wait = source.index("docker compose up -d --no-deps --wait --wait-timeout 120 alloy")
        success = source.index('echo "Platform API:')
        self.assertLess(start, wait)
        self.assertLess(wait, success)
        self.assertIn("set -euo pipefail", source)

    def test_fixture_rejects_stopped_and_unhealthy_collectors(self):
        for state in ('{"Running":false}', '{"Running":true,"Health":{"Status":"unhealthy"}}'):
            with self.subTest(state=state), patch.object(fixture, "run", side_effect=[state, "startup failed"]), \
                    self.assertRaisesRegex(AssertionError, "Collector failed production readiness"):
                fixture.wait_collector("disposable-test")

    def test_fixture_accepts_healthy_collector(self):
        with patch.object(fixture, "run", return_value='{"Running":true,"Health":{"Status":"healthy"}}'):
            fixture.wait_collector("disposable-test")


if __name__ == "__main__":
    unittest.main()
