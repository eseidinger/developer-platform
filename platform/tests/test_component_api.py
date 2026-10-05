import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.identity import Principal
from app.spec import ApplicationEnvelopeV1Alpha2


class ComponentApiTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("https://issuer.example", "person-1", "Person")
        self.body = ApplicationEnvelopeV1Alpha2.model_validate({
            "apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": "shop"},
            "spec": {"components": [
                {"name": "api", "type": "service", "runtime": {"type": "container", "image": "registry/api:v1"},
                 "ports": [{"name": "http", "protocol": "http", "port": 8080}]},
                {"name": "worker", "type": "scheduled", "runtime": {"type": "container", "image": "registry/worker:v1"},
                 "schedule": "*/15 * * * *"},
            ]}})

    def test_v1alpha2_request_resolves_every_component_before_queuing_revision(self):
        queued = Mock(return_value=("operation-1", "queued", 4))
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "resolve_image", side_effect=lambda image: image.replace(":v1", "@sha256:resolved")), \
             patch.object(main, "current_spec", return_value=None), \
             patch.object(main, "connect", return_value=nullcontext(Mock())), patch.object(main, "queue_deploy", queued):
            response = main.provision("shop", self.body, self.principal, if_match=None)

        self.assertEqual(response.status_code, 202)
        spec = queued.call_args.args[3]
        self.assertEqual([component["resolved_image"] for component in spec["components"]],
                         ["registry/api@sha256:resolved", "registry/worker@sha256:resolved"])
        self.assertEqual(spec["components"][1]["concurrency_policy"], "Forbid")
        self.assertNotIn("image", spec)

    def test_component_request_never_queues_if_an_image_cannot_be_resolved(self):
        queued = Mock()
        failure = main.ImageResolutionError("not_found")
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "resolve_image", side_effect=failure), patch.object(main, "queue_deploy", queued):
            with self.assertRaises(main.HTTPException) as error:
                main.provision("shop", self.body, self.principal, if_match=None)
        self.assertEqual(error.exception.status_code, 422)
        queued.assert_not_called()

    def test_component_status_returns_each_observed_component_for_v1alpha2(self):
        spec = {"components": [{"name": "api", "type": "service", "resolved_image": "registry/api@sha256:one"},
                               {"name": "worker", "type": "scheduled", "schedule": "0 * * * *"}]}
        observed = {"components": [{"name": "api", "type": "service", "status": {"state": "ready"}},
                                    {"name": "worker", "type": "scheduled", "state": "idle"}],
                    "observed_at": "2026-10-04T12:00:00+00:00"}
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "current_spec", return_value=(4, spec, "applied")), \
             patch.object(main, "observe_components", return_value=observed) as observe:
            response = main.component_status("shop", self.principal)
        self.assertEqual(response, {"project": "shop", "revision": 4, **observed})
        observe.assert_called_once_with(main.runtime, "shop", spec["components"], main.log)

    def test_component_status_rejects_legacy_revision(self):
        with patch.object(main, "require_permission"), patch.object(main, "current_spec",
                          return_value=(1, {"image": "example:v1"}, "applied")):
            with self.assertRaises(main.HTTPException) as error:
                main.component_status("shop", self.principal)
        self.assertEqual(error.exception.status_code, 409)

    def test_component_log_filter_is_limited_to_known_components(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (1,)
        spec = {"components": [{"name": "worker", "type": "scheduled"}]}
        logs = {"state": "ok", "reason": None, "lines": [], "truncated": False,
                "unavailable_containers": 0, "observed_at": "2026-10-04T12:00:00+00:00"}
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=nullcontext(conn)), \
             patch.object(main, "current_spec", return_value=(4, spec, "applied")), \
             patch.object(main, "observe_logs", return_value=logs) as observe:
            response = main.project_logs("shop", tail=20, since_seconds=None, component="worker",
                                         principal=self.principal)
        self.assertEqual(response, {"project": "shop", **logs})
        observe.assert_called_once_with(main.runtime, "shop", main.log, 20, None, component="worker",
                                        instance=None, search=None, after=None, before=None)

        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=nullcontext(conn)), \
             patch.object(main, "current_spec", return_value=(4, spec, "applied")), \
             patch.object(main, "observe_logs") as rejected:
            with self.assertRaises(main.HTTPException) as error:
                main.project_logs("shop", component="unknown", principal=self.principal)
        self.assertEqual(error.exception.status_code, 404)
        rejected.assert_not_called()


if __name__ == "__main__":
    unittest.main()
