import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.authorization import is_allowed
from app.deployment_credentials import access_scope, initialize, public_record, reconcile_pending_cleanup
from app.identity import Principal
from app import keycloak_credentials


class Result:
    def __init__(self, rows=(), rowcount=0):
        self.rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class CredentialConnection:
    def __init__(self, credential=None, roles=()):
        self.credential = credential
        self.roles = roles
        self.statements = []

    def execute(self, query, params=()):
        self.statements.append((query, params))
        if "FROM deployment_credentials WHERE issuer=" in query:
            return Result([self.credential] if self.credential else [])
        if "SELECT role FROM platform_grants" in query:
            return Result([(role,) for role in self.roles])
        return Result()


class CleanupConnection:
    def __init__(self):
        self.updated = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=()):
        if query.startswith("SELECT credential_id"):
            return Result([("credential-id", "provider-id", "deployment", "shop")])
        if query.startswith("UPDATE deployment_credentials"):
            self.updated = True
            return Result(rowcount=1)
        return Result()


class DeploymentCredentialTests(unittest.TestCase):
    principal = Principal("https://issuer.example", "machine-1", "pipeline")

    def test_schema_contains_expiry_rotation_and_revocation_metadata(self):
        conn = CredentialConnection()
        initialize(conn)
        schema = "\n".join(query for query, _ in conn.statements)
        self.assertIn("expires_at TIMESTAMPTZ NOT NULL", schema)
        self.assertIn("rotated_from UUID", schema)
        self.assertIn("revocation_pending", schema)
        self.assertIn("UNIQUE(issuer, subject)", schema)

    def test_machine_identity_is_limited_to_view_and_deploy_in_its_project(self):
        conn = CredentialConnection((UUID(int=1), "deployment", "shop", True), roles=("developer",))
        self.assertTrue(is_allowed(conn, self.principal, "view", "shop"))
        self.assertTrue(is_allowed(conn, self.principal, "deploy", "shop"))
        self.assertFalse(is_allowed(conn, self.principal, "change", "shop"))
        self.assertFalse(is_allowed(conn, self.principal, "deploy", "other"))

    def test_revoked_or_expired_machine_identity_has_no_permissions(self):
        conn = CredentialConnection((UUID(int=1), "deployment", "shop", False), roles=("developer",))
        self.assertFalse(access_scope(conn, self.principal).active)
        self.assertFalse(is_allowed(conn, self.principal, "view", "shop"))
        self.assertFalse(is_allowed(conn, self.principal, "deploy", "shop"))

    def test_test_runner_uses_its_platform_admin_grant(self):
        conn = CredentialConnection((UUID(int=2), "test-runner", None, True), roles=("platform-admin",))
        self.assertTrue(is_allowed(conn, self.principal, "grant", "shop"))
        self.assertTrue(is_allowed(conn, self.principal, "retire", "other"))

    def test_test_persona_uses_the_standard_role_matrix(self):
        conn = CredentialConnection((UUID(int=3), "test-persona", "shop", True), roles=("viewer",))
        self.assertTrue(is_allowed(conn, self.principal, "view", "shop"))
        self.assertFalse(is_allowed(conn, self.principal, "deploy", "shop"))

    def test_public_record_never_contains_provider_identifiers_or_secret(self):
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        record = public_record(("id-1", "pipeline", "deployment", "shop", "default", "active",
                                now, now, False, None, None, None))
        self.assertEqual(record["name"], "pipeline")
        self.assertNotIn("provider_client_id", record)
        self.assertNotIn("secret", str(record).lower())

    def test_keycloak_adapter_creates_a_service_account_with_platform_audience(self):
        calls = []

        def request(path, **kwargs):
            calls.append((path, kwargs))
            if path.endswith("/token"):
                return 200, {"access_token": "admin-token"}
            if path.startswith("/admin/realms/platform/clients?"):
                return 200, [{"id": "provider-id"}]
            if path.endswith("/service-account-user"):
                return 200, {"id": "machine-subject"}
            return 201, None

        with patch.dict(keycloak_credentials.os.environ, {"KEYCLOAK_PROVISIONER_SECRET": "provisioner-secret"}), \
             patch.object(keycloak_credentials, "_request", side_effect=request), \
             patch.object(keycloak_credentials.secrets, "token_urlsafe", return_value="one-time-secret"), \
             patch.object(keycloak_credentials, "uuid4") as identifier:
            identifier.return_value.hex = "abc"
            created = keycloak_credentials.create_client("shop: pipeline")
        self.assertEqual(created, {"provider_resource_id": "provider-id", "client_id": "platform-ci-abc",
                                   "client_secret": "one-time-secret", "subject": "machine-subject"})
        representation = next(kwargs["body"] for path, kwargs in calls
                              if path == "/admin/realms/platform/clients")
        self.assertTrue(representation["serviceAccountsEnabled"])
        self.assertEqual(representation["protocolMappers"][0]["config"]["included.client.audience"],
                         "platform-api")

    def test_keycloak_client_deletion_is_idempotent_when_provider_already_removed_it(self):
        with patch.object(keycloak_credentials, "_admin_token", return_value="admin-token"), \
             patch.object(keycloak_credentials, "_request", return_value=(404, None)) as request:
            keycloak_credentials.delete_client("provider-id")
        self.assertTrue(request.call_args.kwargs["allow_not_found"])

    def test_pending_provider_cleanup_is_retried_and_audited(self):
        conn = CleanupConnection()
        delete = Mock()
        audit = Mock()
        completed = reconcile_pending_cleanup(lambda: conn, delete, audit, Mock())
        self.assertEqual(completed, 1)
        delete.assert_called_once_with("provider-id")
        self.assertTrue(conn.updated)
        audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
