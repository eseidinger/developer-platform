import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.capacity_admission import _pod_requests, _proposed, assess, snapshot


class CapacityAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.environment = os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.environment)))
        os.environ.update({"CAPACITY_ADMISSION_ENABLED": "true", "CAPACITY_RESERVE_CPU_MILLICORES": "1000",
                           "CAPACITY_RESERVE_MEMORY_MIB": "1024"})

    def test_rejects_request_beyond_allocatable_capacity_after_reserve(self):
        runtime = Mock()
        values = {"Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}], "Pod": []}
        runtime.resources.get.side_effect = lambda api_version, kind: Mock(get=Mock(return_value={"items": values[kind]}))
        result = assess(runtime, {"image": "example", "resources": {"requests": {"cpu": "1100m", "memory": "128Mi"},
                                                                    "limits": {"cpu": "1100m", "memory": "128Mi"}}}, logging.getLogger("test"))
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["reason"], "InsufficientReservedCapacity")

    def test_snapshot_exposes_redacted_request_accounting_with_explicit_units(self):
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
            "Pod": [{"status": {"phase": "Running"}, "spec": {"containers": [
                {"resources": {"requests": {"cpu": "250m", "memory": "128Mi"}}},
            ]}}],
        }
        runtime.resources.get.side_effect = lambda api_version, kind: Mock(
            get=Mock(return_value={"items": values[kind]}))
        self.assertEqual(snapshot(runtime, logging.getLogger("test")), {
            "state": "ok", "enabled": True,
            "allocatable": {"cpu_millicores": 2000, "memory_mib": 2048},
            "requested": {"cpu_millicores": 250, "memory_mib": 128},
            "reserve": {"cpu_millicores": 1000, "memory_mib": 1024},
            "available": {"cpu_millicores": 750, "memory_mib": 896},
        })

    def test_snapshot_accepts_realistic_kubernetes_binary_quantities(self):
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "3900m", "memory": "16007076Ki"}}}],
            "Pod": [{"status": {"phase": "Running"}, "spec": {"containers": [
                {"resources": {"requests": {"cpu": "100m", "memory": "131072Ki"}}},
            ]}}],
        }
        resources = {}

        def resource(api_version, kind):
            resources[kind] = Mock(get=Mock(return_value={"items": values[kind]}))
            return resources[kind]

        runtime.resources.get.side_effect = resource
        result = snapshot(runtime, logging.getLogger("test"))
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["allocatable"], {"cpu_millicores": 3900, "memory_mib": 15631})
        self.assertEqual(result["requested"], {"cpu_millicores": 100, "memory_mib": 128})
        resources["Node"].get.assert_called_once_with(namespace="")
        resources["Pod"].get.assert_called_once_with(namespace="")

    def test_snapshot_distinguishes_invalid_capacity_data_from_api_failure(self):
        runtime = Mock()
        values = {"Node": [{"status": {"allocatable": {"cpu": "invalid", "memory": "2Gi"}}}],
                  "Pod": []}
        runtime.resources.get.side_effect = lambda api_version, kind: Mock(
            get=Mock(return_value={"items": values[kind]}))
        self.assertEqual(snapshot(runtime, logging.getLogger("test")), {
            "state": "unavailable", "enabled": True, "reason": "InvalidKubernetesCapacityData",
        })

        runtime.resources.get.side_effect = RuntimeError("provider failed")
        self.assertEqual(snapshot(runtime, logging.getLogger("test")), {
            "state": "unavailable", "enabled": True, "reason": "KubernetesApiUnavailable",
        })

    def test_snapshot_discloses_disabled_state_without_querying_kubernetes(self):
        os.environ["CAPACITY_ADMISSION_ENABLED"] = "false"
        runtime = Mock()
        self.assertEqual(snapshot(runtime, logging.getLogger("test")),
                         {"state": "disabled", "enabled": False})
        runtime.resources.get.assert_not_called()

    def test_unavailable_runtime_or_invalid_reserve_never_admits(self):
        self.assertEqual(assess(None, {"image": "example"}, logging.getLogger("test"))["state"], "unavailable")
        os.environ["CAPACITY_RESERVE_CPU_MILLICORES"] = "not-a-number"
        runtime = Mock()
        values = {"Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}], "Pod": []}
        runtime.resources.get.side_effect = lambda api_version, kind: Mock(get=Mock(return_value={"items": values[kind]}))
        self.assertEqual(assess(runtime, {"image": "example"}, logging.getLogger("test")),
                         {"state": "unavailable", "reason": "InvalidCapacityReserve"})

    def test_tracing_forwarder_is_included_in_proposed_requests(self):
        component = {"type": "service", "replicas": 2,
                     "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}
        plain = _proposed({"components": [component]})
        traced = _proposed({"components": [{**component, "tracing": {"enabled": True}}]})
        self.assertEqual(traced["cpu"] - plain["cpu"], 50)
        self.assertEqual(traced["memory"] - plain["memory"], 128)

    def test_native_sidecar_and_sequential_init_requests_are_accounted(self):
        sidecar = {"restartPolicy": "Always", "resources": {"requests": {"cpu": "25m", "memory": "64Mi"}}}
        application = {"resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}
        initializer = {"resources": {"requests": {"cpu": "500m", "memory": "256Mi"}}}
        self.assertEqual(_pod_requests({"containers": [application], "initContainers": [sidecar]}),
                         {"cpu": 125, "memory": 192})
        self.assertEqual(_pod_requests({"containers": [application], "initContainers": [sidecar, initializer]}),
                         {"cpu": 525, "memory": 320})
        self.assertEqual(_pod_requests({"containers": [application], "initContainers": [initializer, sidecar]}),
                         {"cpu": 500, "memory": 256})

    def test_snapshot_includes_running_native_sidecar_requests(self):
        runtime = Mock()
        values = {"Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
                  "Pod": [{"status": {"phase": "Running"}, "spec": {
                      "containers": [{"resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}],
                      "initContainers": [{"restartPolicy": "Always",
                                          "resources": {"requests": {"cpu": "25m", "memory": "64Mi"}}}]}}]}
        runtime.resources.get.side_effect = lambda api_version, kind: Mock(get=Mock(return_value={"items": values[kind]}))
        self.assertEqual(snapshot(runtime, logging.getLogger("test"))["requested"],
                         {"cpu_millicores": 125, "memory_mib": 192})


if __name__ == "__main__":
    unittest.main()
