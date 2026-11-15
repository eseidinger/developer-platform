import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import spec


def envelope():
    return {
        "apiVersion": "platform.eseidinger.de/v1",
        "kind": "Application",
        "metadata": {"name": "smoke"},
        "spec": {
            "components": [
                {
                    "name": "web",
                    "type": "service",
                    "runtime": {
                        "type": "container",
                        "image": "hashicorp/http-echo:1.0.0",
                    },
                    "ports": [{"name": "http", "protocol": "http", "port": 5678}],
                    "health": {"readiness": {"path": "/ready", "port": 5678}},
                    "telemetry": {"tracing": {"enabled": True}},
                }
            ],
            "configuration": {"values": {"LOG_LEVEL": "info"}},
        },
    }


class EnvelopeContract(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_rejects_old_formats_and_redundant_metadata(self):
        invalid = [{"name": "smoke", "image": "example:v1"}]
        for version in ("platform.example/v1alpha1", "platform.example/v1alpha2"):
            invalid.append({**envelope(), "apiVersion": version})
        for key, value in (("project", "smoke"), ("environment", "default")):
            body = copy.deepcopy(envelope())
            body["metadata"][key] = value
            invalid.append(body)
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                spec.to_flat(body)

    def test_export_round_trip_keeps_desired_state_and_hides_observations(self):
        internal = spec.to_flat(envelope())
        internal["components"][0]["resolved_image"] = "private-internal-digest"
        exported = spec.from_flat(internal)
        self.assertNotIn("private-internal-digest", str(exported))
        internal["components"][0].pop("resolved_image")
        self.assertEqual(spec.to_flat(exported), internal)

    def test_metadata_name_obeys_project_slug_constraints(self):
        for name in ("Uppercase", "trailing-", "a" * 33, "../other", ""):
            body = {**envelope(), "metadata": {"name": name}}
            with self.subTest(name=name), self.assertRaises(ValueError):
                spec.to_flat(body)

    def test_v1_maps_service_and_scheduled_components(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "api",
                        "type": "service",
                        "runtime": {"type": "container", "image": "registry/api:v1"},
                        "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                        "replicas": 2,
                    },
                    {
                        "name": "worker",
                        "type": "scheduled",
                        "runtime": {
                            "type": "container",
                            "image": "registry/worker:v1",
                            "command": ["python", "-m", "jobs"],
                        },
                        "schedule": "*/15 * * * *",
                    },
                ]
            },
        }
        self.assertEqual(
            spec.to_flat(body),
            {
                "name": "shop",
                "components": [
                    {
                        "name": "api",
                        "type": "service",
                        "image": "registry/api:v1",
                        "replicas": 2,
                        "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                    },
                    {
                        "name": "worker",
                        "type": "scheduled",
                        "image": "registry/worker:v1",
                        "command": ["python", "-m", "jobs"],
                        "schedule": "*/15 * * * *",
                        "time_zone": "UTC",
                        "concurrency_policy": "Forbid",
                        "retry_limit": 6,
                    },
                ],
            },
        )

    def test_service_metrics_opt_in_uses_declared_port_and_bounded_path(self):
        component = {
            "name": "api",
            "type": "service",
            "runtime": {"type": "container", "image": "registry/api:v1"},
            "ports": [{"name": "http", "protocol": "http", "port": 8080}],
            "telemetry": {"metrics": {"port": "http", "path": "/actuator/prometheus"}},
        }
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {"components": [component]},
        }
        self.assertEqual(
            spec.to_flat(body)["components"][0]["metrics"],
            {"port": "http", "path": "/actuator/prometheus"},
        )
        for metrics in (
            {"port": "other", "path": "/metrics"},
            {"port": "http", "path": "//evil"},
            {"port": "http", "path": "/metrics?secret=x"},
        ):
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                spec.to_flat(
                    {
                        **body,
                        "spec": {
                            "components": [
                                {**component, "telemetry": {"metrics": metrics}}
                            ]
                        },
                    }
                )
        traced = spec.to_flat(
            {
                **body,
                "spec": {
                    "components": [
                        {**component, "telemetry": {"tracing": {"enabled": True}}}
                    ]
                },
            }
        )
        self.assertEqual(traced["components"][0]["tracing"], {"enabled": True})

    def test_v1_rejects_invalid_schedule(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "job",
                        "type": "scheduled",
                        "runtime": {"type": "container", "image": "registry/job:v1"},
                        "schedule": "every minute",
                    }
                ]
            },
        }
        with self.assertRaises(ValueError):
            spec.to_flat(body)

    def test_v1_rejects_component_capacity_that_cannot_roll_out_in_quota(self):
        services = [
            {
                "name": f"api-{index}",
                "type": "service",
                "runtime": {"type": "container", "image": f"registry/api:{index}"},
                "replicas": 2,
            }
            for index in range(5)
        ]
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {"components": services},
        }
        with self.assertRaisesRegex(ValueError, "pod quota"):
            spec.to_flat(body)

    def test_v1_exposes_one_declared_service_only(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "api",
                        "type": "service",
                        "runtime": {"type": "container", "image": "registry/api:v1"},
                        "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                        "exposure": "public",
                    }
                ]
            },
        }
        self.assertEqual(spec.to_flat(body)["components"][0]["exposure"], "public")

    def test_v1_maps_http_readiness_and_scheduled_retry_controls(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "web",
                        "type": "service",
                        "runtime": {"type": "container", "image": "registry/web:v1"},
                        "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                        "health": {"readiness": {"path": "/actuator/health/readiness"}},
                    },
                    {
                        "name": "worker",
                        "type": "scheduled",
                        "runtime": {"type": "container", "image": "registry/worker:v1"},
                        "schedule": "* * * * *",
                        "retryLimit": 8,
                        "maxRunSeconds": 600,
                    },
                ]
            },
        }
        flattened = spec.to_flat(body)["components"]
        self.assertEqual(flattened[0]["readiness_path"], "/actuator/health/readiness")
        self.assertEqual(flattened[1]["retry_limit"], 8)
        self.assertEqual(flattened[1]["max_run_seconds"], 600)

    def test_v1_allows_only_operator_approved_outbound_cidr_port(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "api",
                        "type": "service",
                        "runtime": {"type": "container", "image": "registry/api:v1"},
                        "outbound": [{"cidr": "203.0.113.10/32", "port": 443}],
                    }
                ]
            },
        }
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = (
            "203.0.113.0/24",
            "443",
        )
        self.assertEqual(
            spec.to_flat(body)["components"][0]["outbound"],
            [{"cidr": "203.0.113.10/32", "port": 443}],
        )

    def test_v1_allows_scheduled_dns_egress(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "worker",
                        "type": "scheduled",
                        "runtime": {"type": "container", "image": "registry/worker:v1"},
                        "schedule": "* * * * *",
                        "outbound": [{"dns": "api.example.test", "port": 443}],
                    }
                ]
            },
        }
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = (
            "203.0.113.0/24",
            "443",
        )
        with patch(
            "app.spec.resolve_egress_dns",
            return_value={"resolved_cidrs": ["203.0.113.8/32"]},
        ):
            self.assertEqual(
                spec.to_flat(body)["components"][0]["outbound"],
                [{"dns": "api.example.test", "port": 443}],
            )

    def test_v1_rejects_unapproved_or_malformed_operator_egress_policy(self):
        body = {
            "apiVersion": "platform.eseidinger.de/v1",
            "kind": "Application",
            "metadata": {"name": "shop"},
            "spec": {
                "components": [
                    {
                        "name": "api",
                        "type": "service",
                        "runtime": {"type": "container", "image": "registry/api:v1"},
                        "outbound": [{"cidr": "203.0.113.10/32", "port": 443}],
                    }
                ]
            },
        }
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = "", ""
        with self.assertRaisesRegex(ValueError, "not allowed by operator policy"):
            spec.to_flat(body)
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = (
            "not-a-cidr",
            "443",
        )
        with self.assertRaisesRegex(ValueError, "operator egress policy is invalid"):
            spec.to_flat(body)

    def test_operator_egress_denial_has_a_stable_error_code(self):
        self.assertEqual(
            spec.error_code(
                {},
                [
                    {
                        "msg": "Value error, outbound destination is not allowed by operator policy"
                    }
                ],
            ),
            "policy_denied",
        )

    def test_invalid_operator_quota_policy_has_a_stable_error_code(self):
        self.assertEqual(
            spec.error_code(
                {}, [{"msg": "Value error, operator project quota policy is invalid"}]
            ),
            "policy_unavailable",
        )


if __name__ == "__main__":
    unittest.main()
