import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.capacity_admission import assess, snapshot


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


if __name__ == "__main__":
    unittest.main()
