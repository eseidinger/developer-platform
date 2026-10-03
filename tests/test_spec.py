import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
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
            "readiness path": envelope(spec={"application": {**app, "health": {"readiness": {"path": "/x"}}}}),
        }
        for label, body in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                spec.to_flat(body)


if __name__ == "__main__":
    unittest.main()
