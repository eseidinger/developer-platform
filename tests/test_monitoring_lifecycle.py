"""Exercise API authorization and catalog/discovery ordering without a live installation."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from fastapi.testclient import TestClient
from kubernetes.client.exceptions import ApiException
from app import main
from app.identity import AuthenticationError, Principal


class Catalog:
    def __init__(self):
        self.rows = {}
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=()):
        if query.startswith("INSERT INTO projects"):
            name, spec = params
            self.rows[name] = (spec.obj, "provisioning")
        elif query.startswith("UPDATE projects SET status="):
            status = query.split("status='")[1].split("'")[0]
            self.rows[params[0]] = (self.rows[params[0]][0], status)
        elif query.startswith("SELECT name, spec, status"):
            self.result = [(name, *row) for name, row in self.rows.items()]
        elif query.startswith("SELECT status FROM"):
            row = self.rows.get(params[0])
            self.result = [(row[1],)] if row else []
        elif query.startswith("SELECT 1 FROM projects"):
            self.result = [(1,)] if params[0] in self.rows else []
        return self

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0] if self.result else None


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.catalog = Catalog()
        self.runtime = Mock()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        patches = [patch.dict(os.environ, {
            "MONITORING_DISCOVERY_DIR": self.directory.name,
            "APPS_DOMAIN": "apps.localhost", "POSTGRES_IP": "172.30.80.10",
            "DATABASE_KEY": "b" * 32,
            "PLATFORM_AUDIT_PASSWORD": "c" * 32, "PLATFORM_AUDIT_READER_PASSWORD": "d" * 32,
            "OIDC_ISSUER": "https://issuer.example",
            "OIDC_AUDIENCE": "platform-api", "OIDC_JWKS_URL": "https://issuer.example/jwks",
            "PLATFORM_BOOTSTRAP_SUBJECT": "bootstrap-subject"}),
            patch.object(main, "connect", return_value=self.catalog),
            patch.object(main, "runtime", self.runtime),
            patch.object(main, "record_event", return_value=1),
            patch.object(main, "is_allowed", return_value=True),
            patch.object(main, "verifier"),
            patch.object(main, "provision_database"), patch.object(main, "apply")]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.principal = Principal("https://issuer.example", "person-1", "person")
        self.mocks[5].verify.return_value = self.principal
        self.headers = {"Authorization": "Bearer valid-token"}
        self.spec = {"name": "smoke", "image": "example:v1", "probe_profile": "hello-world"}

    def targets(self):
        return json.loads((Path(self.directory.name) / "applications.json").read_text())

    def deploy(self):
        return self.client.put("/projects/smoke", json=self.spec, headers=self.headers)

    def retire(self, headers=None, confirmation="smoke"):
        return self.client.post("/projects/smoke/retire", json={"confirm_name": confirmation},
                                headers=self.headers if headers is None else headers)

    def test_deploy_retry_and_failed_rollout_keep_one_target(self):
        self.assertEqual(self.deploy().status_code, 200)
        self.assertEqual(self.deploy().status_code, 200)
        self.assertEqual(len(self.targets()), 1)
        self.mocks[-1].side_effect = RuntimeError("apply failed")
        self.assertEqual(self.deploy().status_code, 503)
        self.assertEqual(self.catalog.rows["smoke"][1], "failed")
        self.assertEqual(len(self.targets()), 1)

    def test_retire_requires_auth_confirmation_and_absent_namespace(self):
        self.deploy()
        self.assertIn(self.retire(headers={}).status_code, (401, 403))
        self.mocks[5].verify.side_effect = AuthenticationError()
        self.assertEqual(self.retire(headers={"Authorization": "Bearer wrong"}).status_code, 401)
        self.mocks[5].verify.side_effect = None
        self.assertEqual(self.retire(confirmation="different").status_code, 400)
        self.assertEqual(self.retire().status_code, 409)
        self.runtime.resources.get.return_value.get.side_effect = ApiException(status=403)
        self.assertEqual(self.retire().status_code, 503)
        self.assertEqual(len(self.targets()), 1)
        self.assertEqual(self.catalog.rows["smoke"][1], "applied")

    def test_retirement_retry_and_redeployment(self):
        self.deploy()
        self.runtime.resources.get.return_value.get.side_effect = ApiException(status=404)
        response = self.retire()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data_retained"])
        self.assertEqual(self.targets(), [])
        self.assertIn("smoke", self.catalog.rows)
        self.assertEqual(self.retire().status_code, 200)
        self.assertEqual(self.deploy().status_code, 200)
        self.assertEqual(len(self.targets()), 1)

    def test_retirement_publish_failure_reconciles_from_durable_status(self):
        self.deploy()
        self.runtime.resources.get.return_value.get.side_effect = ApiException(status=404)
        with patch.object(main, "publish_catalog", side_effect=OSError):
            self.assertEqual(self.retire().status_code, 503)
        self.assertEqual(self.catalog.rows["smoke"][1], "retired")
        self.assertEqual(len(self.targets()), 1)
        main.publish_catalog(self.catalog)
        self.assertEqual(self.targets(), [])

    def test_invalid_profile_rejected_before_catalog_mutation(self):
        self.spec["probe_profile"] = "arbitrary"
        self.assertEqual(self.deploy().status_code, 422)
        self.assertEqual(self.catalog.rows, {})
        rejected = self.mocks[3].call_args
        self.assertEqual(rejected.args[1:5], ("request.validation", "platform-api", "smoke", "rejected"))

    def test_mutations_and_authentication_denials_are_audited(self):
        self.assertEqual(self.deploy().status_code, 200)
        success = self.mocks[3].call_args
        self.assertEqual(success.args[1:5], ("project.provision", "project", "smoke", "succeeded"))
        self.mocks[5].verify.side_effect = AuthenticationError()
        self.assertEqual(self.retire(headers={"Authorization": "Bearer wrong"}).status_code, 401)
        denied = self.mocks[3].call_args
        self.assertEqual(denied.args[1:5], ("authentication", "platform-api", None, "denied"))

    def test_grant_revocation_blocks_the_next_project_request_and_is_audited(self):
        self.deploy()
        grant = {"issuer": "https://issuer.example", "subject": "person-2", "role": "developer"}
        with patch.object(main, "grant_role") as grant_role:
            response = self.client.put("/projects/smoke/grants", json=grant, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        grant_role.assert_called_once()
        event = self.mocks[3].call_args
        self.assertEqual(event.args[1:5], ("membership.grant", "principal", "https://issuer.example|person-2", "succeeded"))
        with patch.object(main, "revoke_role", return_value=True) as revoke_role:
            response = self.client.request("DELETE", "/projects/smoke/grants", json={
                "issuer": "https://issuer.example", "subject": "person-2"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        revoke_role.assert_called_once()
        self.mocks[4].return_value = False
        self.assertEqual(self.deploy().status_code, 403)
        denied = self.mocks[3].call_args
        self.assertEqual(denied.args[1:5], ("authorization", "project", "smoke", "denied"))
