import importlib.util
import json
import unittest
from pathlib import Path

from app.spec import ApplicationEnvelopeV1Alpha2


ROOT = Path(__file__).resolve().parents[3]
RENDER = ROOT / "examples/web-postgres/render.py"
spec = importlib.util.spec_from_file_location("web_postgres_render", RENDER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WebPostgresTemplateTests(unittest.TestCase):
    def test_rendered_template_matches_application_contract(self):
        body = module.declaration("demo", "ghcr.io/example/web@sha256:" + "a" * 64, binding_id="12345678-1234-1234-1234-123456789abc")
        ApplicationEnvelopeV1Alpha2.model_validate(body)
        self.assertEqual(body["spec"]["components"][0]["health"]["readiness"]["path"], "/health/ready")
        self.assertEqual(body["spec"]["components"][0]["bindings"][0]["bindingId"], "12345678-1234-1234-1234-123456789abc")
        self.assertNotIn("resources", body["spec"])
        self.assertEqual(body["spec"]["configuration"]["values"]["DEMO_FAIL_READY"], "false")
        failed = module.declaration("demo", "ghcr.io/example/web@sha256:" + "a" * 64, fail_ready=True)
        self.assertEqual(failed["spec"]["configuration"]["values"]["DEMO_FAIL_READY"], "true")

    def test_mutable_images_and_invalid_projects_are_rejected(self):
        with self.assertRaises(ValueError):
            module.declaration("demo", "ghcr.io/example/web:latest")
        with self.assertRaises(ValueError):
            module.declaration("../demo", "ghcr.io/example/web@sha256:" + "a" * 64)

    def test_example_policy_is_valid(self):
        from app.access_contract import PolicyCreate
        policy = json.loads((ROOT / "examples/web-postgres/access-policy.json").read_text())
        PolicyCreate.model_validate(policy)


if __name__ == "__main__":
    unittest.main()
