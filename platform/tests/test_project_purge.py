import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.identity import Principal


class Connection:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, statement, *args):
        self.executed.append((str(statement), args))

    def transaction(self):
        return self


class ProjectPurgeTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("https://issuer.example", "admin", "Admin")
        self.scope = {
            "project": "retired-app", "database": "project_retired_app", "role": "project_retired_app",
            "catalog": [], "audit_records_retained": True, "credential_cleanup": {}, "scope_token": "a" * 32,
        }

    def test_platform_administrator_can_purge_confirmed_retired_project(self):
        conn = Connection()
        confirmation = main.ProjectPurge(confirm_name="retired-app", scope_token="a" * 32)
        with patch.object(main, "require_platform_admin") as require_admin, \
             patch.object(main, "connect", return_value=conn), \
             patch.object(main, "current_purge_scope", return_value=self.scope), \
             patch.object(main, "drop_project_database_and_role") as drop_database, \
             patch.object(main, "delete_project_catalog") as delete_catalog, \
             patch.object(main, "publish_catalog") as publish, \
             patch.object(main, "required_audit") as audit:
            result = main.purge_project("retired-app", confirmation, self.principal)

        self.assertEqual(result, {"name": "retired-app", "status": "purged", "audit_records_retained": True})
        require_admin.assert_called_once_with(self.principal)
        drop_database.assert_called_once_with(conn, "retired-app")
        delete_catalog.assert_called_once_with(conn, "retired-app")
        publish.assert_called_once_with(conn)
        self.assertEqual(audit.call_count, 2)

    def test_purge_rejects_stale_scope_without_deleting_data(self):
        conn = Connection()
        confirmation = main.ProjectPurge(confirm_name="retired-app", scope_token="b" * 32)
        with patch.object(main, "require_platform_admin"), \
             patch.object(main, "connect", return_value=conn), \
             patch.object(main, "current_purge_scope", return_value=self.scope), \
             patch.object(main, "drop_project_database_and_role") as drop_database, \
             patch.object(main, "delete_project_catalog") as delete_catalog, \
             patch.object(main, "required_audit"):
            result = main.purge_project("retired-app", confirmation, self.principal)

        self.assertEqual(result.status_code, 409)
        drop_database.assert_not_called()
        delete_catalog.assert_not_called()

    def test_purge_waits_for_credential_revocation(self):
        conn = Connection()
        scope = {**self.scope, "credential_cleanup": {"revocation_pending": 1}}
        confirmation = main.ProjectPurge(confirm_name="retired-app", scope_token="a" * 32)
        with patch.object(main, "require_platform_admin"), \
             patch.object(main, "connect", return_value=conn), \
             patch.object(main, "current_purge_scope", return_value=scope), \
             patch.object(main, "drop_project_database_and_role") as drop_database, \
             patch.object(main, "required_audit"):
            with self.assertRaises(HTTPException) as raised:
                main.purge_project("retired-app", confirmation, self.principal)

        self.assertEqual(raised.exception.status_code, 409)
        drop_database.assert_not_called()


if __name__ == "__main__":
    unittest.main()
