"""Scope expiry, encrypted recovery and real PostgreSQL lifecycle acceptance."""

import os
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import psycopg
from app.identity import Principal
from app.lifecycle import catalog
from app.lifecycle.api import Confirmation
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException


class RecoveryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DATABASE_KEY": "test-only-" * 5})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_recovery_point_is_authenticated_and_bound_to_project_uuid(self):
        identity = uuid4()
        encrypted = catalog.seal(identity, {"secret": "must-not-leak"})
        self.assertNotIn("must-not-leak", encrypted)
        self.assertEqual(
            catalog.unseal(identity, encrypted), {"secret": "must-not-leak"}
        )
        with self.assertRaises(InvalidTag):
            catalog.unseal(uuid4(), encrypted)

    def test_scope_token_expires_and_rejects_changed_inventory(self):
        now = datetime.now(UTC)
        scope = {"project_id": str(uuid4()), "inventory": {"versions": [1, 2]}}
        token = catalog.issue_token(scope, now)
        catalog.check_token(token, scope, now)
        for changed, when in (
            ({**scope, "inventory": {"versions": [1, 3]}}, now),
            (scope, now + timedelta(minutes=16)),
        ):
            with self.subTest(scope=changed), self.assertRaises(HTTPException):
                catalog.check_token(token, changed, when)

    @unittest.skipUnless(
        os.environ.get("LIFECYCLE_TEST_DSN"), "requires an isolated PostgreSQL database"
    )
    def test_acceptance_fences_identity_and_replays_without_duplicate_work(self):
        schema = "lifecycle_test_" + uuid4().hex
        with psycopg.connect(os.environ["LIFECYCLE_TEST_DSN"], autocommit=True) as conn:
            conn.execute("CREATE SCHEMA " + schema)
            try:
                conn.execute("SET search_path TO " + schema)
                conn.execute(
                    "CREATE TABLE projects(name TEXT PRIMARY KEY, project_id UUID UNIQUE NOT NULL,status TEXT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),spec JSONB)"
                )
                catalog.initialize(conn)
                identity = str(uuid4())
                conn.execute(
                    "INSERT INTO projects(name,project_id,status) VALUES('demo',%s,'applied')",
                    (identity,),
                )
                scope = {"project_id": identity, "blockers": []}
                body = Confirmation(
                    confirm_name="demo",
                    confirm_project_id=identity,
                    scope_token=catalog.issue_token(scope),
                )
                principal = Principal("issuer", "admin")
                with conn.transaction():
                    accepted = catalog.enqueue(
                        conn, "demo", "retire", body, principal, scope
                    )
                self.assertEqual(
                    conn.execute(
                        "SELECT status FROM projects WHERE name='demo'"
                    ).fetchone()[0],
                    "retiring",
                )
                replay = catalog.enqueue(
                    conn,
                    "demo",
                    "retire",
                    body,
                    principal,
                    {**scope, "status": "retiring"},
                )
                self.assertEqual(replay["operation_id"], accepted["operation_id"])
                self.assertEqual(
                    conn.execute(
                        "SELECT count(*) FROM project_lifecycle_operations"
                    ).fetchone()[0],
                    1,
                )
                with self.assertRaises(HTTPException):
                    catalog.enqueue(conn, "demo", "purge", body, principal, scope)
            finally:
                conn.execute("DROP SCHEMA " + schema + " CASCADE")
