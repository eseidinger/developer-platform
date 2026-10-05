import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kubernetes.client.exceptions import ApiException

from app import secrets


class FakeCluster:
    """Minimal Secret and Deployment API that stores what the platform writes."""

    def __init__(self):
        self.secrets = {}
        self.version = 0
        self.deployment = {"spec": {"replicas": 1, "template": {"metadata": {}}},
                           "status": {"updatedReplicas": 1, "readyReplicas": 1, "replicas": 1}}
        self.patches = []
        self.resources = Mock()

    @property
    def secret(self):
        return self.secrets.get("app-secrets")

    @property
    def previous(self):
        return self.secrets.get("app-secrets-previous")

    def _bump(self, stored):
        self.version += 1
        stored["metadata"]["resourceVersion"] = str(self.version)
        return json.loads(json.dumps(stored))

    def secret_api(self):
        api = Mock()

        def get(name, namespace):
            if name not in self.secrets:
                raise ApiException(status=404)
            return json.loads(json.dumps(self.secrets[name]))

        def create(body, namespace):
            data = {**body.get("data", {}), **body.get("stringData", {})}
            self.secrets[body["metadata"]["name"]] = {"metadata": body["metadata"], "data": data}
            return self._bump(self.secrets[body["metadata"]["name"]])

        def patch(body, name, namespace, content_type):
            if name not in self.secrets:
                raise ApiException(status=404)
            stored = self.secrets[name]
            self.patches.append(body)
            stored["data"].update(body.get("stringData", {}))
            for key, value in (body.get("data") or {}).items():
                stored["data"].pop(key, None) if value is None else stored["data"].__setitem__(key, value)
            annotations = stored["metadata"].setdefault("annotations", {})
            for key, value in body["metadata"]["annotations"].items():
                annotations.pop(key, None) if value is None else annotations.__setitem__(key, value)
            return self._bump(stored)
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

    def test_rotation_keeps_previous_value_outside_the_mounted_secret_until_confirmed(self):
        fake = cluster()
        secrets.write_secret(fake, "smoke", "API_TOKEN", "one")
        self.assertIsNone(fake.previous)
        self.assertEqual(secrets.read_secret(fake, "smoke")["secrets"][0]["state"], "active")
        secrets.write_secret(fake, "smoke", "API_TOKEN", "two")
        self.assertEqual(fake.previous["data"], {"API_TOKEN": "one"})
        self.assertEqual(fake.secret["data"], {"API_TOKEN": "two"})
        entry = secrets.read_secret(fake, "smoke")["secrets"][0]
        self.assertEqual((entry["version"], entry["state"]), (2, "rotating"))
        self.assertNotIn("one", json.dumps(secrets.read_secret(fake, "smoke")))
        self.assertTrue(secrets.confirm_secret(fake, "smoke", "API_TOKEN"))
        self.assertEqual(fake.previous["data"], {})
        self.assertFalse(secrets.confirm_secret(fake, "smoke", "API_TOKEN"))
        self.assertEqual(secrets.read_secret(fake, "smoke")["secrets"][0]["state"], "active")

    def test_revert_restores_previous_value_as_new_version(self):
        fake = cluster()
        self.assertIsNone(secrets.revert_secret(fake, "smoke", "API_TOKEN"))
        secrets.write_secret(fake, "smoke", "API_TOKEN", "one")
        secrets.write_secret(fake, "smoke", "API_TOKEN", "two")
        self.assertIsNotNone(secrets.revert_secret(fake, "smoke", "API_TOKEN"))
        self.assertEqual(fake.secret["data"], {"API_TOKEN": "one"})
        self.assertEqual(fake.previous["data"], {})
        self.assertEqual(secrets.read_secret(fake, "smoke")["secrets"][0]["version"], 3)

    def test_remove_and_new_value_discard_stale_previous(self):
        fake = cluster()
        secrets.write_secret(fake, "smoke", "A_KEY", "one")
        secrets.write_secret(fake, "smoke", "A_KEY", "two")
        secrets.remove_secret(fake, "smoke", "A_KEY")
        self.assertEqual(fake.previous["data"], {})
        secrets.write_secret(fake, "smoke", "A_KEY", "three")
        self.assertEqual(secrets.read_secret(fake, "smoke")["secrets"][0]["version"], 1)

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
