import json
import sys
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.identity import Principal


class Result:
    def __init__(self, rows=(), rowcount=0):
        self.rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class CredentialApiConnection:
    credential_id = UUID("00000000-0000-0000-0000-000000000123")
    replacement_id = UUID("00000000-0000-0000-0000-000000000124")

    def __init__(self):
        self.now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        self.public = (self.credential_id, "pipeline", "deployment", "shop", "default", "active",
                       self.now, self.now + timedelta(days=30), False, None, None, None)
        self.replacement = (self.replacement_id, "pipeline-r-12345678", "deployment", "shop", "default",
                            "active", self.now, self.now + timedelta(days=30), False, None,
                            self.credential_id, None)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=()):
        self.statements.append((query, params))
        if query.startswith("SELECT 1 FROM projects"):
            return Result([(1,)])
        if "INSERT INTO deployment_credentials" in query:
            return Result([self.replacement if "rotated_from" in query else self.public])
        if query.startswith("SELECT credential_id, name"):
            return Result([self.public])
        if query.startswith("SELECT name, status"):
            return Result([("pipeline", "active", True)])
        if query.startswith("SELECT status, expires_at"):
            return Result([("active", True)])
        if query.startswith("UPDATE deployment_credentials\n                    SET expires_at"):
            return Result([(self.now + timedelta(hours=1),)])
        if query.startswith("SELECT provider_resource_id"):
            return Result([("provider-id", "https://issuer.example", "machine-subject", "active")])
        if query.startswith("DELETE FROM platform_grants"):
            return Result(rowcount=1)
        return Result()


class DeploymentCredentialApiTests(unittest.TestCase):
    principal = Principal("https://issuer.example", "admin-subject", "Project Admin")

    def test_create_returns_secret_once_and_list_is_secret_free(self):
        conn = CredentialApiConnection()
        provider = {"provider_resource_id": "provider-id", "client_id": "platform-ci-abc",
                    "client_secret": "one-time-secret", "subject": "machine-subject"}
        verifier = Mock(issuer="https://issuer.example")
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=conn), patch.object(main, "verifier", verifier), \
             patch.object(main, "create_credential_client", return_value=provider):
            created = main.create_deployment_credential(
                "shop", main.DeploymentCredentialCreate(name="pipeline"), self.principal)
            listed = main.list_deployment_credentials("shop", self.principal)

        created_body = json.loads(created.body)
        self.assertEqual(created_body["client_secret"], "one-time-secret")
        self.assertEqual(created_body["client_id"], "platform-ci-abc")
        self.assertNotIn("secret", str(listed).lower())
        self.assertNotIn("client_id", str(listed))

    def test_revoke_removes_platform_grant_before_provider_client(self):
        conn = CredentialApiConnection()
        events = []

        def provider_delete(provider_id):
            events.append(("provider", provider_id, len(conn.statements)))

        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=conn), \
             patch.object(main, "delete_credential_client", side_effect=provider_delete):
            result = main.revoke_deployment_credential("shop", conn.credential_id, self.principal)

        grant_delete = next(index for index, (query, _) in enumerate(conn.statements)
                            if query.startswith("DELETE FROM platform_grants"))
        self.assertLess(grant_delete, events[0][2])
        self.assertEqual(result["status"], "revoked")

    def test_provider_failure_leaves_immediate_denial_and_retryable_cleanup(self):
        conn = CredentialApiConnection()
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=conn), \
             patch.object(main, "delete_credential_client",
                          side_effect=main.CredentialProviderError("unavailable")):
            result = main.revoke_deployment_credential("shop", conn.credential_id, self.principal)
        self.assertEqual(result.status_code, 202)
        self.assertEqual(json.loads(result.body)["status"], "revocation_pending")
        self.assertTrue(any(query.startswith("DELETE FROM platform_grants") for query, _ in conn.statements))

    def test_rotate_links_replacement_and_bounds_predecessor_expiry(self):
        conn = CredentialApiConnection()
        provider = {"provider_resource_id": "replacement-provider", "client_id": "platform-ci-new",
                    "client_secret": "replacement-secret", "subject": "replacement-subject"}
        verifier = Mock(issuer="https://issuer.example")
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=conn), patch.object(main, "verifier", verifier), \
             patch.object(main, "create_credential_client", return_value=provider), \
             patch.object(main, "uuid4", return_value=UUID("12345678-0000-0000-0000-000000000000")):
            rotated = main.rotate_deployment_credential(
                "shop", conn.credential_id,
                main.DeploymentCredentialRotate(expires_in_days=20, overlap_hours=1), self.principal)

        body = json.loads(rotated.body)
        self.assertEqual(body["credential_id"], str(conn.replacement_id))
        self.assertEqual(body["rotated_from"], str(conn.credential_id))
        self.assertEqual(body["predecessor_id"], str(conn.credential_id))
        self.assertEqual(body["client_secret"], "replacement-secret")
        insert = next(params for query, params in conn.statements
                      if "INSERT INTO deployment_credentials" in query and "rotated_from" in query)
        self.assertEqual(insert[-1], conn.credential_id)
        overlap = next(params for query, params in conn.statements
                       if query.startswith("UPDATE deployment_credentials\n                    SET expires_at"))
        self.assertEqual(overlap, (1, conn.credential_id))


if __name__ == "__main__":
    unittest.main()
