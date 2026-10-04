import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
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


if __name__ == "__main__":
    unittest.main()
