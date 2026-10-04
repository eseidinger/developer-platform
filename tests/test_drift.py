import logging
import sys
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import Mock

from kubernetes.client.exceptions import ApiException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.drift import observe_drift

SPEC = {"name": "smoke", "image": "example:v1", "resolved_image": "example@sha256:" + "a" * 64,
        "resources": {"limits": {"cpu": "1", "memory": "512Mi"}}}


def deployment(image=SPEC["resolved_image"], replicas=1, resources=None):
    resources = resources or {"requests": {"cpu": "100m", "memory": "128Mi"},
                              "limits": {"cpu": "1", "memory": "512Mi"}}
    return {"spec": {"replicas": replicas, "template": {"spec": {"containers": [
        {"name": "app", "image": image, "resources": resources}]}}}}


def runtime_with(value=None, error=None):
    resource = Mock()
    if error:
        resource.get.side_effect = error
    else:
        resource.get.return_value = value
    runtime = Mock()
    runtime.resources.get.return_value = resource
    return runtime


class DriftTests(unittest.TestCase):
    log = logging.getLogger("test")

    def test_matching_deployment_is_in_sync_even_with_equivalent_quantity_spellings(self):
        result = observe_drift(runtime_with(deployment()), "smoke", SPEC, self.log)
        self.assertEqual(result, {"state": "in_sync", "differences": []})

    def test_manual_changes_are_reported_field_by_field(self):
        changed = deployment(image="example@sha256:" + "b" * 64, replicas=3,
                             resources={"requests": {"cpu": "100m", "memory": "128Mi"},
                                        "limits": {"cpu": "2", "memory": "512Mi"}})
        result = observe_drift(runtime_with(changed), "smoke", SPEC, self.log)
        self.assertEqual(result["state"], "drifted")
        self.assertEqual({d["field"] for d in result["differences"]},
                         {"image", "replicas", "resources.limits.cpu"})
        replicas = next(d for d in result["differences"] if d["field"] == "replicas")
        self.assertEqual((replicas["desired"], replicas["observed"]), (1, 3))

    def test_missing_deployment_and_observer_failures_are_not_reported_as_drift(self):
        missing = observe_drift(runtime_with(error=ApiException(status=404)), "smoke", SPEC, self.log)
        self.assertEqual(missing["state"], "not_found")
        failed = observe_drift(runtime_with(error=ApiException(status=500)), "smoke", SPEC, self.log)
        self.assertEqual(failed["state"], "unknown")
        self.assertEqual(observe_drift(None, "smoke", SPEC, self.log)["state"], "unknown")

    def test_component_revision_reports_service_and_scheduled_drift(self):
        deployment_resource, cronjob_resource = Mock(), Mock()
        deployment_resource.get.return_value = deployment(replicas=2)
        cronjob_resource.get.return_value = {"spec": {"schedule": "0 * * * *", "timeZone": "UTC",
                                                         "concurrencyPolicy": "Forbid"}}
        runtime = Mock()
        runtime.resources.get.side_effect = lambda **kwargs: (
            deployment_resource if kwargs["kind"] == "Deployment" else cronjob_resource)
        spec = {"components": [
            {"name": "api", "type": "service", "image": "example:v1", "resolved_image": SPEC["resolved_image"],
             "replicas": 1, "resources": SPEC["resources"]},
            {"name": "worker", "type": "scheduled", "image": "example:job", "schedule": "*/15 * * * *",
             "time_zone": "UTC", "concurrency_policy": "Forbid"},
        ]}
        result = observe_drift(runtime, "smoke", spec, self.log)
        self.assertEqual(result["state"], "drifted")
        self.assertEqual({(d["component"], d["field"]) for d in result["differences"]},
                         {("api", "replicas"), ("worker", "schedule")})


class ScanTests(unittest.TestCase):
    log = logging.getLogger("test")

    def scan(self, rows, observations, state):
        from app.drift import scan_once
        events = []
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        conn.execute.return_value.fetchall.return_value = rows
        with unittest.mock.patch("app.drift.observe_drift", side_effect=observations):
            scan_once(lambda: conn, Mock(), lambda *a: events.append(a[1:]) or 1, state, self.log)
        return events

    def test_audits_only_transitions_and_resolution(self):
        rows = [("smoke", 4, SPEC)]
        drifted = {"state": "drifted", "differences": [{"field": "replicas", "desired": 1, "observed": 2}]}
        ok = {"state": "in_sync", "differences": []}
        state = {}
        first = self.scan(rows, [drifted], state)
        self.assertEqual([e[0] for e in first], ["project.drift.detected"])
        self.assertEqual(first[0][5], {"revision": 4, "fields": ["replicas"]})
        self.assertEqual(self.scan(rows, [drifted], state), [])
        self.assertEqual([e[0] for e in self.scan(rows, [ok], state)], ["project.drift.resolved"])
        self.assertEqual(self.scan(rows, [ok], state), [])

    def test_unknown_observations_keep_the_previous_state_and_vanished_projects_are_forgotten(self):
        rows = [("smoke", 4, SPEC)]
        drifted = {"state": "drifted", "differences": [{"field": "image", "desired": "a", "observed": "b"}]}
        state = {}
        self.scan(rows, [drifted], state)
        self.assertEqual(self.scan(rows, [{"state": "unknown", "differences": []}], state), [])
        self.assertEqual(self.scan(rows, [drifted], state), [])
        self.scan([], [], state)
        self.assertEqual(state, {})
