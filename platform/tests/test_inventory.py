import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.inventory import observe_inventory


def item(name, spec=None, status=None):
    return {"metadata": {"name": name}, "spec": spec or {}, "status": status or {}}


class InventoryTests(unittest.TestCase):
    def test_lists_safe_project_topology_and_managed_data_service(self):
        runtime = Mock()
        resources = runtime.resources.get
        values = {
            "Deployment": [item("web", {"replicas": 2}, {"ready_replicas": 1})],
            "Pod": [item("web-1", status={"phase": "Running"})], "Service": [item("web")],
            "Ingress": [item("web")], "ResourceQuota": [item("project", status={"hard": {"cpu": "2"}})],
            "LimitRange": [item("defaults")]}
        resources.side_effect = lambda api_version, kind: Mock(get=Mock(return_value={"items": values[kind]}))
        result = observe_inventory(runtime, "smoke", logging.getLogger("test"))
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["deployments"][0], {"name": "web", "replicas": 2, "ready_replicas": 1})
        self.assertEqual(result["instances"][0]["phase"], "Running")
        self.assertEqual(result["data_services"], [{"type": "postgresql", "name": "managed", "scope": "project"}])

    def test_provider_failure_is_not_reported_as_empty_inventory(self):
        runtime = Mock()
        runtime.resources.get.side_effect = RuntimeError("private detail")
        result = observe_inventory(runtime, "smoke", logging.getLogger("test"))
        self.assertEqual(result, {"state": "unavailable", "reason": "KubernetesApiUnavailable"})


if __name__ == "__main__":
    unittest.main()
