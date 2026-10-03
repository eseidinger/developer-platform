import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from kubernetes.client.exceptions import ApiException

from app import secrets


class FakeCluster:
    """Minimal Secret and Deployment API that stores what the platform writes."""

    def __init__(self):
        self.secret = None
        self.version = 0
        self.deployment = {"spec": {"replicas": 1, "template": {"metadata": {}}},
                           "status": {"updatedReplicas": 1, "readyReplicas": 1, "replicas": 1}}
        self.patches = []
        self.resources = Mock()

    def _bump(self):
        self.version += 1
        self.secret["metadata"]["resourceVersion"] = str(self.version)
        return json.loads(json.dumps(self.secret))

    def secret_api(self):
        api = Mock()

        def get(name, namespace):
            if self.secret is None:
                raise ApiException(status=404)
            return json.loads(json.dumps(self.secret))

        def create(body, namespace):
            self.secret = {"metadata": body["metadata"], "data": dict(body["stringData"])}
            return self._bump()

        def patch(body, name, namespace, content_type):
            if self.secret is None:
                raise ApiException(status=404)
            self.patches.append(body)
            self.secret["data"].update(body.get("stringData", {}))
            for key, value in (body.get("data") or {}).items():
                if value is None:
                    self.secret["data"].pop(key, None)
            annotations = self.secret["metadata"].setdefault("annotations", {})
            for key, value in body["metadata"]["annotations"].items():
                annotations.pop(key, None) if value is None else annotations.__setitem__(key, value)
            return self._bump()
        api.get, api.create, api.patch = get, create, patch
        return api

    def deployment_api(self):
        api = Mock()
        api.get.side_effect = lambda name, namespace: self.deployment

        def patch(body, name, namespace, content_type, field_manager):
            self.deployment["spec"]["template"]["metadata"].setdefault("annotations", {}).update(
                body["spec"]["template"]["metadata"]["annotations"])
            return self.deployment
        api.patch = patch
        return api


def cluster():
    fake = FakeCluster()
    fake.resources.get.side_effect = lambda api_version, kind: (
        fake.secret_api() if kind == "Secret" else fake.deployment_api())
    return fake


class SecretStoreTests(unittest.TestCase):
    def test_validation(self):
        secrets.validate_secret_name("DB_PASSWORD")
        for bad in ("PGPASSWORD", "1A", "a-b", "A" * 51, 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                secrets.validate_secret_name(bad)
        for bad in ("", 5, None, "x" * 8193, "a\x00"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                secrets.validate_secret_value(bad)

    def test_write_lists_names_only_and_pins_version_to_pods(self):
        fake = cluster()
        self.assertIsNone(secrets.read_secret(fake, "smoke"))
        version = secrets.write_secret(fake, "smoke", "API_TOKEN", "s3cret-value")
        self.assertTrue(secrets.roll_pods(fake, "smoke", version))
        listed = secrets.read_secret(fake, "smoke")
        self.assertEqual([s["name"] for s in listed["secrets"]], ["API_TOKEN"])
        self.assertNotIn("s3cret-value", json.dumps(listed))
        self.assertEqual(secrets.observe_secret_activation(fake, "smoke", listed["version"])["state"], "active")
        again = secrets.write_secret(fake, "smoke", "API_TOKEN", "rotated")
        self.assertNotEqual(again, version)
        self.assertEqual(secrets.observe_secret_activation(fake, "smoke", again)["state"], "pending")
        secrets.roll_pods(fake, "smoke", again)
        self.assertEqual(secrets.observe_secret_activation(fake, "smoke", again)["state"], "active")

    def test_remove_and_missing_deployment(self):
        fake = cluster()
        secrets.write_secret(fake, "smoke", "A_KEY", "v")
        version = secrets.remove_secret(fake, "smoke", "A_KEY")
        self.assertEqual(secrets.read_secret(fake, "smoke")["secrets"], [])
        fake.resources.get.side_effect = lambda api_version, kind: (
            fake.secret_api() if kind == "Secret" else Mock(patch=Mock(side_effect=ApiException(status=404))))
        self.assertFalse(secrets.roll_pods(fake, "smoke", version))

    def test_unavailable_cluster_is_reported_not_leaked(self):
        with self.assertRaises(secrets.SecretsUnavailable):
            secrets.read_secret(None, "smoke")
        broken = Mock()
        broken.resources.get.return_value.get.side_effect = ApiException(status=500)
        with self.assertRaises(secrets.SecretsUnavailable):
            secrets.read_secret(broken, "smoke")


if __name__ == "__main__":
    unittest.main()
