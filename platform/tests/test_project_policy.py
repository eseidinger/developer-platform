import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.manifests import component_resources
from app.main import Project
from app.project_policy import quota_for, validate_component_capacity


class ProjectQuotaPolicyTests(unittest.TestCase):
    def setUp(self):
        self.environment = os.environ.copy()
        self.addCleanup(self.restore_environment)

    def restore_environment(self):
        os.environ.clear()
        os.environ.update(self.environment)

    def test_project_override_drives_manifest_and_admission(self):
        os.environ["PROJECT_QUOTAS_JSON"] = ('{"default":{"pods":"4"},'
                                              '"shop":{"requests.cpu":"600m","limits.cpu":"1200m"}}')
        quota = quota_for("shop")
        self.assertEqual(quota["pods"], "4")
        self.assertEqual(quota["requests.cpu"], "600m")
        manifests = component_resources("shop", [{"name": "api", "type": "service",
            "resolved_image": "registry/api@sha256:one"}], "172.30.80.10", "secret")
        resource_quota = next(item for item in manifests if item["kind"] == "ResourceQuota")
        self.assertEqual(resource_quota["spec"]["hard"], quota)
        with self.assertRaisesRegex(ValueError, "resource quota"):
            validate_component_capacity("shop", [{"name": "api", "type": "service", "replicas": 1,
                "resources": {"requests": {"cpu": "400m", "memory": "128Mi"},
                              "limits": {"cpu": "800m", "memory": "256Mi"}}}])

    def test_malformed_operator_policy_fails_closed(self):
        os.environ["PROJECT_QUOTAS_JSON"] = '{'
        with self.assertRaisesRegex(ValueError, "operator project quota policy is invalid"):
            quota_for("shop")

    def test_flat_project_is_rejected_before_operation_when_its_quota_is_exceeded(self):
        os.environ["PROJECT_QUOTAS_JSON"] = '{"shop":{"requests.cpu":"150m","limits.cpu":"600m"}}'
        with self.assertRaisesRegex(ValueError, "resource quota"):
            Project.model_validate({"name": "shop", "image": "registry/app:v1",
                                    "resources": {"requests": {"cpu": "100m"}, "limits": {"cpu": "500m"}}})


if __name__ == "__main__":
    unittest.main()
