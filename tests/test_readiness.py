import logging
import sys
import unittest
from unittest.mock import Mock
from pathlib import Path

from kubernetes.client.exceptions import ApiException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.readiness import observe_deployment


def condition(condition_type, status, reason=None):
    return {"type": condition_type, "status": status, "reason": reason}


def deployment(*, ready=0, updated=0, conditions=None):
    return {
        "metadata": {"generation": 2},
        "spec": {"replicas": 1, "template": {"spec": {"containers": [
            {"name": "app", "image": "example:v1"},
        ]}}},
        "status": {
            "observedGeneration": 2,
            "readyReplicas": ready,
            "updatedReplicas": updated,
            "conditions": conditions or [condition("Progressing", "True", "NewReplicaSetAvailable")],
        },
    }


class Resource:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.value

    def list(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.value


class Resources:
    def __init__(self, deployment_resource, pods_resource):
        self.deployment_resource = deployment_resource
        self.pods_resource = pods_resource

    def get(self, *, api_version, kind):
        if (api_version, kind) == ("apps/v1", "Deployment"):
            return self.deployment_resource
        if (api_version, kind) == ("v1", "Pod"):
            return self.pods_resource
        raise AssertionError(f"Unexpected Kubernetes resource {api_version}/{kind}")


class ReadinessObservationTests(unittest.TestCase):
    def setUp(self):
        self.deployment = Resource(deployment(ready=1, updated=1))
        self.pods = Resource({"items": [{
            "status": {
                "conditions": [condition("Ready", "True")],
                "containerStatuses": [{
                    "name": "app", "ready": True, "image": "example:v1",
                    "imageID": "docker-pullable://example@sha256:abc",
                }],
            },
        }]})
        self.runtime = Mock()
        self.runtime.resources = Resources(self.deployment, self.pods)
        self.log = Mock(spec=logging.Logger)

    def observe(self):
        return observe_deployment(self.runtime, "smoke", "example:v1", self.log)

    def test_reports_ready_and_active_image(self):
        result = self.observe()

        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["desired_replicas"], 1)
        self.assertEqual(result["ready_replicas"], 1)
        self.assertEqual(result["desired_image"], "example:v1")
        self.assertEqual(result["deployment_image"], "example:v1")
        self.assertEqual(result["active_images"], ["example:v1"])
        self.assertEqual(result["active_image_ids"], ["docker-pullable://example@sha256:abc"])
        self.assertIsNone(result["reason"])
        self.assertEqual(self.deployment.calls, [{"name": "smoke", "namespace": "project-smoke"}])
        self.assertEqual(self.pods.calls, [{
            "namespace": "project-smoke",
            "label_selector": "app.kubernetes.io/name=smoke",
        }])

    def test_reports_image_pull_diagnostic_while_rollout_is_progressing(self):
        self.deployment.value = deployment(conditions=[
            condition("Progressing", "True", "ReplicaSetUpdated"),
        ])
        self.pods.value = {"items": [{
            "status": {"containerStatuses": [{
                "name": "app", "ready": False,
                "state": {"waiting": {"reason": "ImagePullBackOff"}},
            }]},
        }]}

        result = self.observe()

        self.assertEqual(result["state"], "progressing")
        self.assertEqual(result["reason"], "ImagePullBackOff")
        self.assertEqual(result["ready_replicas"], 0)

    def test_reports_unschedulable_pod_diagnostic(self):
        self.deployment.value = deployment()
        self.pods.value = {"items": [{
            "status": {"conditions": [
                condition("PodScheduled", "False", "Unschedulable"),
            ]},
        }]}

        result = self.observe()

        self.assertEqual(result["state"], "progressing")
        self.assertEqual(result["reason"], "Unschedulable")

    def test_reports_progress_deadline_failure(self):
        self.deployment.value = deployment(conditions=[
            condition("Progressing", "False", "ProgressDeadlineExceeded"),
        ])

        result = self.observe()

        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["reason"], "ProgressDeadlineExceeded")

    def test_does_not_apply_old_rollout_failure_to_a_different_desired_image(self):
        self.deployment.value = deployment(conditions=[
            condition("Progressing", "False", "ProgressDeadlineExceeded"),
        ])
        self.deployment.value["spec"]["template"]["spec"]["containers"][0]["image"] = "example:v0"

        result = self.observe()

        self.assertEqual(result["state"], "progressing")
        self.assertEqual(result["reason"], "DeploymentImageMismatch")

    def test_missing_deployment_is_a_distinct_observation(self):
        self.deployment.error = ApiException(status=404)

        result = self.observe()

        self.assertEqual(result["state"], "not_found")
        self.assertEqual(result["desired_replicas"], 1)
        self.assertEqual(result["ready_replicas"], 0)
        self.assertEqual(result["reason"], "DeploymentNotFound")

    def test_kubernetes_error_is_visible_without_leaking_exception_text(self):
        self.deployment.error = RuntimeError("private provider detail")

        result = self.observe()

        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["reason"], "ObserverUnavailable")
        self.assertNotIn("private provider detail", str(result))
        self.log.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
