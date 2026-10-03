import logging
import sys
import unittest
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
