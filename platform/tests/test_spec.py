import sys
import unittest
import os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import spec

API = "platform.example/v1alpha1"


def envelope(**changes):
    body = {
        "apiVersion": API, "kind": "Application", "metadata": {"name": "smoke"},
        "spec": {"application": {
            "runtime": {"type": "container", "image": "hashicorp/http-echo:1.0.0"},
            "endpoints": [{"name": "http", "protocol": "http", "port": 5678, "exposure": "public"}],
            "scaling": {"minInstances": 1, "maxInstances": 1},
            "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
            "health": {"readiness": {"profile": "hello-world"}}},
            "resources": [{"name": "database", "type": "postgres", "profile": "shared-dev",
                           "deletionPolicy": "retain"}]},
    }
    body.update(changes)
    return body


class EnvelopeContract(unittest.TestCase):
    def setUp(self):
        self.environment = os.environ.copy()
        self.addCleanup(self.restore_environment)

    def restore_environment(self):
        os.environ.clear()
        os.environ.update(self.environment)

    def test_flat_body_passes_through_unchanged(self):
        flat = {"name": "smoke", "image": "example:v1"}
        self.assertEqual(spec.to_flat(flat), flat)

    def test_envelope_maps_to_the_flat_project_fields(self):
        self.assertEqual(spec.to_flat(envelope()), {
            "name": "smoke", "image": "hashicorp/http-echo:1.0.0", "port": 5678,
            "probe_profile": "hello-world", "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1000m", "memory": "512Mi"}}})

    def test_minimal_envelope_relies_on_defaults(self):
        body = {"apiVersion": API, "kind": "Application", "metadata": {"name": "a"},
                "spec": {"application": {"runtime": {"type": "container", "image": "x:1"}}}}
        self.assertEqual(spec.to_flat(body), {"name": "a", "image": "x:1"})

    def test_configuration_values_map_to_flat_field(self):
        app = envelope()["spec"]["application"]
        body = envelope(spec={"application": app, "configuration": {"values": {"B": "2", "A": "1"}}})
        self.assertEqual(spec.to_flat(body)["configuration"], {"A": "1", "B": "2"})

    def test_unsupported_versions_kinds_and_capabilities_are_rejected(self):
        app = envelope()["spec"]["application"]
        cases = {
            "version": envelope(apiVersion="platform.example/v2"),
            "kind": envelope(kind="Job"),
            "other project": envelope(metadata={"name": "smoke", "project": "other"}),
            "environment": envelope(metadata={"name": "smoke", "environment": "prod"}),
            "unknown top level": envelope(status={}),
            "unknown spec field": envelope(spec={"application": app, "components": []}),
            "autoscaling": envelope(spec={"application": {**app, "scaling": {"minInstances": 1, "maxInstances": 3}}}),
            "two endpoints": envelope(spec={"application": {**app, "endpoints": app["endpoints"] * 2}}),
            "internal endpoint": envelope(spec={"application": {**app, "endpoints": [
                {"name": "http", "protocol": "http", "port": 80, "exposure": "internal"}]}}),
            "runtime type": envelope(spec={"application": {**app, "runtime": {"type": "vm", "image": "x"}}}),
            "other resource": envelope(spec={"application": app, "resources": [
                {"name": "q", "type": "queue", "profile": "x", "deletionPolicy": "retain"}]}),
            "delete policy": envelope(spec={"application": app, "resources": [
                {"name": "database", "type": "postgres", "profile": "shared-dev", "deletionPolicy": "delete"}]}),
            "configuration secrets": envelope(spec={"application": app, "configuration": {"secrets": {}}}),
            "reserved configuration": envelope(spec={"application": app, "configuration": {"values": {"PGHOST": "b"}}}),
        }
        for label, body in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                spec.to_flat(body)

    def test_http_readiness_path_maps_to_the_flat_project_fields(self):
        app = envelope()["spec"]["application"]
        body = envelope(spec={"application": {**app, "health": {"readiness": {
            "path": "/actuator/health/readiness", "port": 5678}}}})
        self.assertEqual(spec.to_flat(body)["readiness_path"], "/actuator/health/readiness")
        self.assertEqual(spec.to_flat(body)["readiness_port"], 5678)

    def test_v1alpha2_maps_service_and_scheduled_components(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application",
                "metadata": {"name": "shop"}, "spec": {"components": [
                    {"name": "api", "type": "service", "runtime": {"type": "container", "image": "registry/api:v1"},
                     "ports": [{"name": "http", "protocol": "http", "port": 8080}], "replicas": 2},
                    {"name": "worker", "type": "scheduled", "runtime": {"type": "container", "image": "registry/worker:v1",
                        "command": ["python", "-m", "jobs"]}, "schedule": "*/15 * * * *"}]}}
        self.assertEqual(spec.to_flat(body), {"name": "shop", "components": [
            {"name": "api", "type": "service", "image": "registry/api:v1", "replicas": 2,
             "ports": [{"name": "http", "protocol": "http", "port": 8080}]},
            {"name": "worker", "type": "scheduled", "image": "registry/worker:v1",
             "command": ["python", "-m", "jobs"], "schedule": "*/15 * * * *", "time_zone": "UTC",
             "concurrency_policy": "Forbid", "retry_limit": 6}]})

    def test_v1alpha2_rejects_invalid_schedule(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"},
                "spec": {"components": [{"name": "job", "type": "scheduled",
                    "runtime": {"type": "container", "image": "registry/job:v1"}, "schedule": "every minute"}]}}
        with self.assertRaises(ValueError):
            spec.to_flat(body)

    def test_v1alpha2_rejects_component_capacity_that_cannot_roll_out_in_quota(self):
        services = [{"name": f"api-{index}", "type": "service",
                     "runtime": {"type": "container", "image": f"registry/api:{index}"}, "replicas": 2}
                    for index in range(5)]
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application",
                "metadata": {"name": "shop"}, "spec": {"components": services}}
        with self.assertRaisesRegex(ValueError, "pod quota"):
            spec.to_flat(body)

    def test_v1alpha2_exposes_one_declared_service_only(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"}, "spec": {"components": [
            {"name": "api", "type": "service", "runtime": {"type": "container", "image": "registry/api:v1"},
             "ports": [{"name": "http", "protocol": "http", "port": 8080}], "exposure": "public"}]}}
        self.assertEqual(spec.to_flat(body)["components"][0]["exposure"], "public")

    def test_v1alpha2_maps_http_readiness_and_scheduled_retry_controls(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"}, "spec": {"components": [
            {"name": "web", "type": "service", "runtime": {"type": "container", "image": "registry/web:v1"},
             "ports": [{"name": "http", "protocol": "http", "port": 8080}],
             "health": {"readiness": {"path": "/actuator/health/readiness"}}},
            {"name": "worker", "type": "scheduled", "runtime": {"type": "container", "image": "registry/worker:v1"},
             "schedule": "* * * * *", "retryLimit": 8, "maxRunSeconds": 600}]}}
        flattened = spec.to_flat(body)["components"]
        self.assertEqual(flattened[0]["readiness_path"], "/actuator/health/readiness")
        self.assertEqual(flattened[1]["retry_limit"], 8)
        self.assertEqual(flattened[1]["max_run_seconds"], 600)

    def test_v1alpha2_allows_only_operator_approved_outbound_cidr_port(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"}, "spec": {"components": [
            {"name": "api", "type": "service", "runtime": {"type": "container", "image": "registry/api:v1"},
             "outbound": [{"cidr": "203.0.113.10/32", "port": 443}]}]}}
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = "203.0.113.0/24", "443"
        self.assertEqual(spec.to_flat(body)["components"][0]["outbound"], [{"cidr": "203.0.113.10/32", "port": 443}])

    def test_v1alpha2_allows_scheduled_dns_egress(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"}, "spec": {"components": [
            {"name": "worker", "type": "scheduled", "runtime": {"type": "container", "image": "registry/worker:v1"},
             "schedule": "* * * * *", "outbound": [{"dns": "api.example.test", "port": 443}]}]}}
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = "203.0.113.0/24", "443"
        with patch("app.spec.resolve_egress_dns", return_value={"resolved_cidrs": ["203.0.113.8/32"]}):
            self.assertEqual(spec.to_flat(body)["components"][0]["outbound"],
                             [{"dns": "api.example.test", "port": 443}])

    def test_v1alpha2_rejects_unapproved_or_malformed_operator_egress_policy(self):
        body = {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"}, "spec": {"components": [
            {"name": "api", "type": "service", "runtime": {"type": "container", "image": "registry/api:v1"},
             "outbound": [{"cidr": "203.0.113.10/32", "port": 443}]}]}}
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = "", ""
        with self.assertRaisesRegex(ValueError, "not allowed by operator policy"):
            spec.to_flat(body)
        os.environ["ALLOWED_EGRESS_CIDRS"], os.environ["ALLOWED_EGRESS_PORTS"] = "not-a-cidr", "443"
        with self.assertRaisesRegex(ValueError, "operator egress policy is invalid"):
            spec.to_flat(body)

    def test_operator_egress_denial_has_a_stable_error_code(self):
        self.assertEqual(spec.error_code({}, [{"msg": "Value error, outbound destination is not allowed by operator policy"}]),
                         "policy_denied")

    def test_invalid_operator_quota_policy_has_a_stable_error_code(self):
        self.assertEqual(spec.error_code({}, [{"msg": "Value error, operator project quota policy is invalid"}]),
                         "policy_unavailable")


if __name__ == "__main__":
    unittest.main()
