import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.capacity_admission import _pod_requests, _proposed, assess, snapshot


class CapacityAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.environment = os.environ.copy()
        self.addCleanup(
            lambda: (os.environ.clear(), os.environ.update(self.environment))
        )
        os.environ.update(
            {
                "CAPACITY_ADMISSION_ENABLED": "true",
                "CAPACITY_RESERVE_CPU_MILLICORES": "1000",
                "CAPACITY_RESERVE_MEMORY_MIB": "1024",
                "CAPACITY_HOST_OVERHEAD_CPU_MILLICORES": "0",
                "CAPACITY_HOST_OVERHEAD_MEMORY_MIB": "0",
                "CAPACITY_KUBERNETES_OVERHEAD_MEMORY_MIB": "0",
            }
        )
        self.host = {
            "state": "ok",
            "captured_at": 100,
            "capacity": {"cpu_millicores": 2000, "memory_mib": 2048},
            "nodes": {"node": {"cpu_millicores": 2000, "memory_mib": 2048}},
            "services": [],
        }
        self.reader = patch(
            "app.capacity_admission.read_snapshot", side_effect=lambda: self.host
        ).start()
        self.addCleanup(patch.stopall)

    def runtime(self, values):
        for node in values["Node"]:
            node.setdefault("metadata", {"name": "node"})
        runtime = Mock()
        runtime.resources.get.side_effect = lambda api_version, kind: Mock(
            get=Mock(return_value={"items": values[kind]})
        )
        return runtime

    def test_rejects_request_beyond_allocatable_capacity_after_reserve(self):
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
            "Pod": [],
        }
        runtime = self.runtime(values)
        result = assess(
            runtime,
            {
                "image": "example",
                "resources": {
                    "requests": {"cpu": "1100m", "memory": "128Mi"},
                    "limits": {"cpu": "1100m", "memory": "128Mi"},
                },
            },
            logging.getLogger("test"),
        )
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["reason"], "InsufficientReservedCapacity")

    def test_snapshot_exposes_redacted_request_accounting_with_explicit_units(self):
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
            "Pod": [
                {
                    "status": {"phase": "Running"},
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "requests": {"cpu": "250m", "memory": "128Mi"}
                                }
                            },
                        ]
                    },
                }
            ],
        }
        runtime = self.runtime(values)
        result = snapshot(runtime, logging.getLogger("test"))
        self.assertEqual(
            {
                key: result[key]
                for key in (
                    "state",
                    "enabled",
                    "allocatable",
                    "requested",
                    "reserve",
                    "available",
                )
            },
            {
                "state": "ok",
                "enabled": True,
                "allocatable": {"cpu_millicores": 2000, "memory_mib": 2048},
                "requested": {"cpu_millicores": 250, "memory_mib": 128},
                "reserve": {"cpu_millicores": 1000, "memory_mib": 1024},
                "available": {"cpu_millicores": 750, "memory_mib": 896},
            },
        )

    def test_snapshot_accepts_realistic_kubernetes_binary_quantities(self):
        runtime = Mock()
        values = {
            "Node": [
                {"status": {"allocatable": {"cpu": "3900m", "memory": "16007076Ki"}}}
            ],
            "Pod": [
                {
                    "status": {"phase": "Running"},
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "131072Ki"}
                                }
                            },
                        ]
                    },
                }
            ],
        }
        resources = {}
        values["Node"][0]["metadata"] = {"name": "node"}
        self.host["capacity"] = {"cpu_millicores": 4000, "memory_mib": 16384}
        self.host["nodes"]["node"] = {"cpu_millicores": 4000, "memory_mib": 16384}

        def resource(api_version, kind):
            resources[kind] = Mock(get=Mock(return_value={"items": values[kind]}))
            return resources[kind]

        runtime.resources.get.side_effect = resource
        result = snapshot(runtime, logging.getLogger("test"))
        self.assertEqual(result["state"], "ok")
        self.assertEqual(
            result["allocatable"], {"cpu_millicores": 3900, "memory_mib": 15631}
        )
        self.assertEqual(
            result["requested"], {"cpu_millicores": 100, "memory_mib": 128}
        )
        resources["Node"].get.assert_called_once_with(namespace="")
        resources["Pod"].get.assert_called_once_with(namespace="")

    def test_snapshot_distinguishes_invalid_capacity_data_from_api_failure(self):
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "invalid", "memory": "2Gi"}}}],
            "Pod": [],
        }
        runtime = self.runtime(values)
        self.assertEqual(
            snapshot(runtime, logging.getLogger("test")),
            {
                "state": "unavailable",
                "enabled": True,
                "reason": "InvalidKubernetesCapacityData",
            },
        )

        runtime.resources.get.side_effect = RuntimeError("provider failed")
        self.assertEqual(
            snapshot(runtime, logging.getLogger("test")),
            {
                "state": "unavailable",
                "enabled": True,
                "reason": "KubernetesApiUnavailable",
            },
        )

    def test_snapshot_discloses_disabled_state_without_querying_kubernetes(self):
        os.environ["CAPACITY_ADMISSION_ENABLED"] = "false"
        runtime = Mock()
        self.assertEqual(
            snapshot(runtime, logging.getLogger("test")),
            {"state": "disabled", "enabled": False},
        )
        runtime.resources.get.assert_not_called()

    def test_unavailable_runtime_or_invalid_reserve_never_admits(self):
        self.assertEqual(
            assess(None, {"image": "example"}, logging.getLogger("test"))["state"],
            "unavailable",
        )
        os.environ["CAPACITY_RESERVE_CPU_MILLICORES"] = "not-a-number"
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
            "Pod": [],
        }
        runtime = self.runtime(values)
        self.assertEqual(
            assess(runtime, {"image": "example"}, logging.getLogger("test")),
            {"state": "unavailable", "reason": "InvalidCapacityReserve"},
        )

    def test_tracing_forwarder_is_included_in_proposed_requests(self):
        component = {
            "type": "service",
            "replicas": 2,
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}},
        }
        plain = _proposed({"components": [component]})
        traced = _proposed(
            {"components": [{**component, "tracing": {"enabled": True}}]}
        )
        self.assertEqual(traced["cpu"] - plain["cpu"], 50)
        self.assertEqual(traced["memory"] - plain["memory"], 128)

    def test_native_sidecar_and_sequential_init_requests_are_accounted(self):
        sidecar = {
            "restartPolicy": "Always",
            "resources": {"requests": {"cpu": "25m", "memory": "64Mi"}},
        }
        application = {"resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}
        initializer = {"resources": {"requests": {"cpu": "500m", "memory": "256Mi"}}}
        self.assertEqual(
            _pod_requests({"containers": [application], "initContainers": [sidecar]}),
            {"cpu": 125, "memory": 192},
        )
        self.assertEqual(
            _pod_requests(
                {"containers": [application], "initContainers": [sidecar, initializer]}
            ),
            {"cpu": 525, "memory": 320},
        )
        self.assertEqual(
            _pod_requests(
                {"containers": [application], "initContainers": [initializer, sidecar]}
            ),
            {"cpu": 500, "memory": 256},
        )

    def test_snapshot_includes_running_native_sidecar_requests(self):
        runtime = Mock()
        values = {
            "Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
            "Pod": [
                {
                    "status": {"phase": "Running"},
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"}
                                }
                            }
                        ],
                        "initContainers": [
                            {
                                "restartPolicy": "Always",
                                "resources": {
                                    "requests": {"cpu": "25m", "memory": "64Mi"}
                                },
                            }
                        ],
                    },
                }
            ],
        }
        runtime = self.runtime(values)
        self.assertEqual(
            snapshot(runtime, logging.getLogger("test"))["requested"],
            {"cpu_millicores": 125, "memory_mib": 192},
        )

    def test_single_host_cpu_is_not_tripled_and_host_reserve_is_not_deducted_from_nodes(
        self,
    ):
        os.environ.update(
            {
                "CAPACITY_RESERVE_CPU_MILLICORES": "2000",
                "CAPACITY_RESERVE_MEMORY_MIB": "8192",
                "CAPACITY_HOST_OVERHEAD_CPU_MILLICORES": "2000",
                "CAPACITY_HOST_OVERHEAD_MEMORY_MIB": "1024",
                "CAPACITY_KUBERNETES_OVERHEAD_MEMORY_MIB": "4096",
            }
        )
        names = ["server", "agent-a", "agent-b"]
        self.host = {
            "state": "ok",
            "captured_at": 100,
            "capacity": {"cpu_millicores": 16000, "memory_mib": 31337},
            "nodes": {
                name: {"cpu_millicores": 16000, "memory_mib": memory}
                for name, memory in zip(names, [2048, 4096, 4096])
            },
            "services": [
                {
                    "name": "shared",
                    "cpu_millicores": 12250,
                    "memory_mib": 19712,
                    "cpu_unbounded": False,
                }
            ],
        }
        values = {
            "Node": [
                {
                    "metadata": {"name": name},
                    "status": {"allocatable": {"cpu": "16", "memory": memory}},
                }
                for name, memory in zip(names, ["2147483Ki", "4294967Ki", "4294967Ki"])
            ],
            "Pod": [
                {
                    "status": {"phase": "Running"},
                    "spec": {
                        "containers": [
                            {
                                "resources": {
                                    "requests": {"cpu": "1200m", "memory": "1388Mi"}
                                }
                            }
                        ]
                    },
                }
            ],
        }
        result = snapshot(self.runtime(values), logging.getLogger("test"))
        self.assertEqual(
            result["kubernetes"]["reported_allocatable"],
            {"cpu_millicores": 48000, "memory_mib": 10485},
        )
        self.assertEqual(
            result["allocatable"], {"cpu_millicores": 16000, "memory_mib": 10240}
        )
        self.assertEqual(
            result["available"], {"cpu_millicores": 550, "memory_mib": 4756}
        )
        self.assertEqual(result["host"]["available"]["memory_mib"], 5117)
        self.assertEqual(result["limiting"], {"cpu": "host", "memory": "kubernetes"})
        # Both sides independently reject requests exceeding their budget.
        runtime = self.runtime(values)
        for request in (
            {"cpu": "600m", "memory": "128Mi"},
            {"cpu": "100m", "memory": "5Gi"},
        ):
            self.assertEqual(
                assess(
                    runtime,
                    {"resources": {"requests": request}},
                    logging.getLogger("test"),
                )["state"],
                "rejected",
            )
        self.assertEqual(
            assess(
                runtime,
                {"resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}},
                logging.getLogger("test"),
            )["state"],
            "accepted",
        )

    def test_missing_host_data_and_mismatched_nodes_fail_closed(self):
        self.host = {"state": "unavailable", "reason": "HostCapacitySnapshotStale"}
        self.assertEqual(
            snapshot(Mock(), logging.getLogger("test"))["reason"],
            "HostCapacitySnapshotStale",
        )
        self.host = {
            "state": "ok",
            "captured_at": 100,
            "capacity": {"cpu_millicores": 2000, "memory_mib": 2048},
            "nodes": {"different-node": {"cpu_millicores": 2000, "memory_mib": 2048}},
            "services": [],
        }
        runtime = self.runtime(
            {
                "Node": [{"status": {"allocatable": {"cpu": "2", "memory": "2Gi"}}}],
                "Pod": [],
            }
        )
        self.assertEqual(
            snapshot(runtime, logging.getLogger("test"))["reason"],
            "HostKubernetesTopologyMismatch",
        )


if __name__ == "__main__":
    unittest.main()
