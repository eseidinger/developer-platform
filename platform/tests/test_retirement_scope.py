import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.retirement import removal_scope


class RetirementScopeTests(unittest.TestCase):
    def test_component_scope_includes_each_workload_and_retains_database(self):
        spec = {"components": [
            {"name": "api", "type": "service", "resolved_image": "example/api@sha256:one",
             "ports": [{"name": "http", "port": 8080}]},
            {"name": "worker", "type": "scheduled", "resolved_image": "example/worker@sha256:two",
             "schedule": "0 * * * *"},
        ]}
        scope = removal_scope("shop", 4, spec, "apps.localhost")
        self.assertIn({"kind": "Deployment", "name": "api"}, scope["removes"])
        self.assertIn({"kind": "Service", "name": "api"}, scope["removes"])
        self.assertIn({"kind": "CronJob", "name": "worker"}, scope["removes"])
        self.assertEqual(scope["retains"]["database"], "project_shop")


if __name__ == "__main__":
    unittest.main()
