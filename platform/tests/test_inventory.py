import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.inventory import observe_inventory
from app import main
from app.identity import Principal


def item(name, spec=None, status=None):
    return {"metadata": {"name": name}, "spec": spec or {}, "status": status or {}}


class InventoryTests(unittest.TestCase):
    def test_lists_safe_project_topology_and_managed_data_service(self):
        runtime = Mock()
        resources = runtime.resources.get
        values = {
            "Deployment": [item("web", {"replicas": 2, "template": {"spec": {"containers": [
                {"name": "web", "resources": {"requests": {"cpu": "100m"}, "limits": {"cpu": "500m"}}}]}}}, {"ready_replicas": 1})],
            "Pod": [item("web-1", status={"phase": "Running"})], "Service": [item("web")],
            "Ingress": [item("web")], "ResourceQuota": [item("project", status={"hard": {"cpu": "2"}})],
            "LimitRange": [item("defaults")]}
        resources.side_effect = lambda api_version, kind: Mock(get=Mock(return_value={"items": values[kind]}))
        result = observe_inventory(runtime, "smoke", logging.getLogger("test"))
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["deployments"][0], {"name": "web", "replicas": 2, "ready_replicas": 1,
                         "containers": [{"name": "web", "requests": {"cpu": "100m"}, "limits": {"cpu": "500m"}}]})
        self.assertEqual(result["instances"][0]["phase"], "Running")
        self.assertEqual(result["declared_totals"], {"requests": {"cpu_millicores": 200, "memory_bytes": 0},
                                                       "limits": {"cpu_millicores": 1000, "memory_bytes": 0}})
        self.assertEqual(result["data_services"], [{"type": "postgresql", "name": "managed", "scope": "project"}])

    def test_provider_failure_is_not_reported_as_empty_inventory(self):
        runtime = Mock()
        runtime.resources.get.side_effect = RuntimeError("private detail")
        result = observe_inventory(runtime, "smoke", logging.getLogger("test"))
        self.assertEqual(result, {"state": "unavailable", "reason": "KubernetesApiUnavailable"})

    def test_resource_endpoint_combines_inventory_with_labelled_usage(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = ("applied",)
        inventory = {"state": "ok", "reason": None}
        usage = {"state": "missing", "reason": "NoMetricsForProject", "pods": [], "totals": None}
        principal = Principal("https://issuer.example", "person", "Person")
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=__import__("contextlib").nullcontext(conn)), \
             patch.object(main, "observe_inventory", return_value=inventory), \
             patch.object(main, "observe_usage", return_value=usage):
            result = main.resource_inventory("smoke", principal)
        self.assertEqual(result, {"project": "smoke", **inventory, "usage": usage})


if __name__ == "__main__":
    unittest.main()
