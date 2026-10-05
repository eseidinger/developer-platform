import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.capacity_admission import assess


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
