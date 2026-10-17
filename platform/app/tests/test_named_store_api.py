"""Authorization boundaries for resource administration and personal credentials."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.identity import Principal
from app.stores import api, catalog


class StoreApiTests(TestCase):
    def setUp(self):
        self.principal = Principal("https://fixture.invalid", "admin")
        self.conn = Mock()
        self.conn.transaction.return_value = nullcontext()
        self.control = SimpleNamespace(connect=lambda: nullcontext(self.conn),
            current_principal=lambda: self.principal, access_scope=Mock(return_value=None),
            require_permission=Mock(), require_platform_admin=Mock(), required_audit=Mock(),
            actor_for=Mock(), is_allowed=Mock(return_value=True))
        app = FastAPI()
        api.install(app, self.control)
        self.client = TestClient(app)
        self.resource_id = uuid4()
        self.grant_id = uuid4()

    def test_foreign_resource_administration_checks_owning_project(self):
        self.control.require_permission.side_effect = HTTPException(403, "Denied")
        with patch.object(catalog, "resource", return_value={"owner_project": "alpha"}):
            response = self.client.get(f"/v1/resources/{self.resource_id}")
        self.assertEqual(response.status_code, 403)
        self.control.require_permission.assert_called_once_with(self.principal, "manage", "alpha")

    def test_platform_admin_does_not_implicitly_receive_another_humans_credential(self):
        credential_id = uuid4()
        with patch.object(catalog, "_object", return_value={"grant_id": str(self.grant_id)}), \
                patch.object(catalog, "grant", return_value={"kind": "human", "issuer": self.principal.issuer,
                    "subject": "someone-else"}), patch.object(api.providers, "get") as provider:
            response = self.client.get(f"/v1/store-access/credentials/{credential_id}")
        self.assertEqual(response.status_code, 404)
        provider.assert_not_called()

    def test_machine_identity_cannot_administer_resources_or_issue_human_credentials(self):
        self.control.access_scope.return_value = {"kind": "automation"}
        with patch.object(catalog, "create_resource") as create, patch.object(catalog, "issue") as issue:
            response = self.client.post("/v1/projects/alpha/resources", json={"name": "db", "provider": "postgresql"})
            credential = self.client.post(f"/v1/store-access/{self.grant_id}/credentials")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(credential.status_code, 403)
        create.assert_not_called(); issue.assert_not_called()

    def test_purge_requires_exact_version_resource_and_owner(self):
        row = {"resource_id": str(self.resource_id), "owner_project": "alpha", "state": "retired",
               "observed_state": "retired", "version": 3}
        from app.stores.contract import Purge
        for body in (Purge(version=2, confirm_resource_id=self.resource_id, confirm_owner_project="alpha"),
                     Purge(version=3, confirm_resource_id=uuid4(), confirm_owner_project="alpha"),
                     Purge(version=3, confirm_resource_id=self.resource_id, confirm_owner_project="beta")):
            with self.assertRaises(catalog.Conflict):
                catalog.request_purge(self.conn, row, body)
        self.conn.execute.assert_not_called()

    def test_cross_project_scope_increase_requires_fresh_request(self):
        row = {"resource_id": str(self.resource_id), "kind": "binding", "consumer_project": "beta",
               "mode": "read-only"}
        with patch.object(catalog, "grant", return_value=row), \
                patch.object(catalog, "resource", return_value={"owner_project": "alpha"}), \
                patch.object(catalog, "change_mode") as change:
            response = self.client.put(f"/v1/resource-grants/{self.grant_id}/mode", json={"version": 1, "mode": "read-write"})
        self.assertEqual(response.status_code, 409)
        change.assert_not_called()

    def test_resource_id_and_secret_material_are_independent_of_display_name(self):
        import os
        with patch.dict(os.environ, {"DATABASE_KEY": "x" * 32}):
            first = catalog.secret_for(self.resource_id)
            self.assertEqual(first, catalog.secret_for(str(self.resource_id)))
            self.assertNotEqual(first, catalog.secret_for(uuid4()))
        self.assertNotIn("alpha", catalog.identifier(self.resource_id))


if __name__ == "__main__":
    main()
