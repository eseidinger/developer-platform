"""A component change must not roll its unchanged peers just for attribution."""

import copy
import unittest
from unittest.mock import Mock, patch

from app.workload_context import CONTEXT, FINGERPRINT, pod_template, preserve, stamp
from kubernetes.client.exceptions import ApiException

from app import main


def workload(kind="Deployment"):
    template = {
        "metadata": {"labels": {"component": "peer"}},
        "spec": {"containers": [{"name": "peer", "image": "fixture:v1"}]},
    }
    spec = {"template": template}
    if kind == "CronJob":
        spec = {"schedule": "* * * * *", "jobTemplate": {"spec": spec}}
    return {
        "apiVersion": "apps/v1" if kind == "Deployment" else "batch/v1",
        "kind": kind,
        "metadata": {"name": "peer", "namespace": "project-fixture"},
        "spec": spec,
    }


class WorkloadContextTests(unittest.TestCase):
    def test_unchanged_peers_retain_context_across_multiple_application_revisions(self):
        for kind in ("Deployment", "CronJob"):
            raw = workload(kind)
            live = stamp(raw, 1, "first")
            for revision in (2, 3, 4):
                desired = stamp(raw, revision, "operation-" + str(revision))
                preserved = preserve(desired, live)
                self.assertEqual(pod_template(preserved), pod_template(live))
                self.assertEqual(
                    pod_template(desired)["metadata"]["annotations"][CONTEXT[0]],
                    str(revision),
                )
                live = preserved
            self.assertNotIn("annotations", raw["metadata"])

    def test_real_workload_changes_receive_current_context(self):
        for change in (
            "image",
            "configuration",
            "binding",
            "restart",
            "replicas",
            "schedule",
        ):
            raw = workload("CronJob" if change == "schedule" else "Deployment")
            live = stamp(raw, 1, "first")
            changed = copy.deepcopy(raw)
            container = pod_template(changed)["spec"]["containers"][0]
            if change == "image":
                container["image"] = "fixture:v2"
            elif change == "configuration":
                container["env"] = [{"name": "SETTING", "value": "new"}]
            elif change == "binding":
                container["envFrom"] = [{"secretRef": {"name": "binding-new"}}]
            elif change == "restart":
                pod_template(changed)["metadata"]["annotations"] = {
                    "platform.example/restarted-by": "restart-2"
                }
            elif change == "replicas":
                changed["spec"]["replicas"] = 2
            else:
                changed["spec"]["schedule"] = "*/2 * * * *"
            desired = stamp(changed, 2, "second")
            self.assertNotEqual(
                desired["metadata"]["annotations"][FINGERPRINT],
                live["metadata"]["annotations"][FINGERPRINT],
            )
            self.assertEqual(preserve(desired, live), desired)

    def test_legacy_or_incomplete_context_is_adopted_once(self):
        desired = stamp(workload(), 2, "second")
        self.assertEqual(preserve(desired, workload()), desired)
        incomplete = copy.deepcopy(desired)
        del pod_template(incomplete)["metadata"]["annotations"][CONTEXT[1]]
        self.assertEqual(preserve(desired, incomplete), desired)

    def test_apply_repairs_drift_without_restarting_an_unchanged_peer(self):
        raw = workload()
        live = stamp(raw, 1, "first")
        # Repair actual cluster drift even when the accepted desired state is
        # unchanged. Skipping apply entirely would leave this drift behind.
        pod_template(live)["spec"]["containers"][0]["image"] = "drifted:image"
        desired = stamp(raw, 2, "second")
        resource = Mock(namespaced=True)
        resource.get.return_value.to_dict.return_value = live
        with patch.object(main, "runtime") as runtime:
            runtime.resources.get.return_value = resource
            main.apply(desired)
        applied = resource.patch.call_args.kwargs["body"]
        self.assertEqual(
            pod_template(applied)["spec"]["containers"][0]["image"], "fixture:v1"
        )
        self.assertEqual(
            pod_template(applied)["metadata"]["annotations"][CONTEXT[1]], "first"
        )

    def test_apply_only_treats_missing_workloads_as_a_first_deployment(self):
        desired = stamp(workload(), 2, "second")
        for status in (404, 403, 503):
            resource = Mock(namespaced=True)
            resource.get.side_effect = ApiException(status=status)
            with patch.object(main, "runtime") as runtime:
                runtime.resources.get.return_value = resource
                if status == 404:
                    main.apply(desired)
                    resource.patch.assert_called_once()
                else:
                    with self.assertRaises(ApiException):
                        main.apply(desired)
                    resource.patch.assert_not_called()
