"""Real SQL lifecycle execution with a disposable in-memory Kubernetes boundary."""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import psycopg
from app.identity import Principal
from app.lifecycle import catalog, erasure, worker
from app.spec import to_flat
from fastapi.testclient import TestClient
from kubernetes.client.exceptions import ApiException
from psycopg.types.json import Jsonb

from app import main


class Kubernetes:
    def __init__(self):
        self.objects = {
            ("Namespace", "project-demo", None): {"metadata": {"name": "project-demo"}},
            ("Secret", "app-secrets", "project-demo"): {
                "metadata": {"name": "app-secrets"},
                "data": {"PASSWORD": "cHJpdmF0ZQ=="},
            },
        }
        self.resources = self

    def get(self, api_version=None, kind=None, name=None, namespace=None):
        if kind:
            return Mock(
                get=lambda **kw: self.read(kind, **kw),
                delete=lambda **kw: self.delete(kind, **kw),
            )
        raise AssertionError("missing resource kind")

    def read(self, kind, name, namespace=None):
        value = self.objects.get((kind, name, namespace))
        if value is None:
            raise ApiException(status=404)
        return copy.deepcopy(value)

    def delete(self, kind, name, namespace=None):
        self.objects.pop((kind, name, namespace), None)
        if kind == "Namespace":
            for key in list(self.objects):
                if key[2] == name:
                    del self.objects[key]

    def apply(self, manifest):
        meta = manifest["metadata"]
        self.objects[(manifest["kind"], meta["name"], meta.get("namespace"))] = (
            copy.deepcopy(manifest)
        )


@unittest.skipUnless(
    os.environ.get("LIFECYCLE_TEST_DSN"), "requires isolated PostgreSQL"
)
class LifecycleExecutionTests(unittest.TestCase):
    def setUp(self):
        self.schema = "lifecycle_" + uuid4().hex
        self.environment = patch.dict(
            os.environ,
            {
                "DATABASE_KEY": "test-only-" * 5,
                "APPS_DOMAIN": "apps.test",
                "PLATFORM_MAINTENANCE_DIR": tempfile.mkdtemp(),
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.runtime = Kubernetes()
        dsn = os.environ["LIFECYCLE_TEST_DSN"]
        self.admin = psycopg.connect(dsn, autocommit=True)
        self.admin.execute("CREATE SCHEMA " + self.schema)
        self.addCleanup(self.cleanup)
        self.connect = lambda: psycopg.connect(
            dsn, autocommit=True, options="-c search_path=" + self.schema + ",public"
        )
        self.patchers = [
            patch.object(main, "connect", side_effect=self.connect),
            patch.object(main, "runtime", self.runtime),
            patch.object(main, "apply", side_effect=self.runtime.apply),
            patch.object(main, "required_audit"),
            patch.object(main, "publish_catalog"),
            patch.object(main, "require_platform_admin"),
            patch.object(main, "require_permission"),
            patch.object(main, "access_scope", return_value=None),
        ]
        for guard in self.patchers:
            guard.start()
            self.addCleanup(guard.stop)
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE projects(name TEXT PRIMARY KEY,spec JSONB,status TEXT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            main.initialize_catalog(conn)
            catalog.initialize(conn)
            main.initialize_authorization(conn)
            main.initialize_deployment_credentials(conn)
            main.human_database_access.initialize(conn)
            main.store_catalog.initialize(conn)
            main.access_store.initialize(conn)
            main.ai_store.initialize(conn)
            main.ai_changes.initialize(conn)
            conn.execute(
                "CREATE TABLE data_service_recovery_requests(request_id UUID PRIMARY KEY,project TEXT)"
            )
            conn.execute("CREATE SCHEMA IF NOT EXISTS platform_audit")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS platform_audit.events(scope JSONB,target_kind TEXT,target_id TEXT,operation_id TEXT,detail JSONB)"
            )
            spec = to_flat(
                {
                    "apiVersion": "platform.eseidinger.de/v1",
                    "kind": "Application",
                    "metadata": {"name": "demo"},
                    "spec": {
                        "components": [
                            {
                                "name": "web",
                                "type": "service",
                                "runtime": {"type": "container", "image": "example:v1"},
                            }
                        ]
                    },
                }
            )
            spec["components"][0]["resolved_image"] = "example@sha256:" + "a" * 64
            self.identity = conn.execute(
                "INSERT INTO projects(name,spec,status) VALUES('demo',%s,'applied') RETURNING project_id::text",
                (Jsonb(spec),),
            ).fetchone()[0]
            main.ensure_default_application(conn, self.identity, "demo", spec)
            conn.execute(
                "ALTER TABLE platform_audit.events ADD COLUMN IF NOT EXISTS detail JSONB"
            )
        self.principal = Principal("issuer", "admin")
        main.app.dependency_overrides[main.current_principal] = lambda: self.principal
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client = TestClient(main.app)

    def cleanup(self):
        self.admin.execute("DROP SCHEMA " + self.schema + " CASCADE")
        self.admin.close()

    def start(self, action):
        prefix = (
            "/v1/projects/demo" if action == "retire" else "/v1/operator/projects/demo"
        )
        preview = self.client.get(
            prefix
            + (
                "/retirement-preview"
                if action == "retire"
                else "/" + action + "-preview"
            )
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        body = {
            "confirm_name": "demo",
            "confirm_project_id": self.identity,
            "scope_token": preview.json()["scope_token"],
        }
        response = self.client.post(prefix + "/" + action, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()["operation_id"]

    def operation(self, identity):
        with self.connect() as conn:
            return catalog.read(conn, identity)

    def test_retirement_preserves_secrets_and_restore_rebuilds_same_identity(self):
        retirement = self.start("retire")
        worker.process_one(main)
        self.assertEqual(self.operation(retirement)["state"], "succeeded")
        self.assertNotIn(("Namespace", "project-demo", None), self.runtime.objects)
        with self.connect() as conn:
            encrypted = conn.execute(
                "SELECT encrypted_snapshot FROM project_recovery_points"
            ).fetchone()[0]
            self.assertNotIn("cHJpdmF0ZQ==", encrypted)
        restore = self.start("restore")
        worker.process_one(main)
        self.assertEqual(
            self.runtime.objects[("Secret", "app-secrets", "project-demo")]["data"][
                "PASSWORD"
            ],
            "cHJpdmF0ZQ==",
        )
        # Polling must preserve credentials issued after snapshot preparation.
        self.runtime.objects[("Secret", "app-secrets", "project-demo")]["data"][
            "ACCESS_NEW_TOKEN"
        ] = "bmV3"
        worker.process_one(main)
        self.assertEqual(
            self.runtime.objects[("Secret", "app-secrets", "project-demo")]["data"][
                "ACCESS_NEW_TOKEN"
            ],
            "bmV3",
        )
        with self.connect() as conn:
            conn.execute("UPDATE application_operations SET state='succeeded'")
            conn.execute("UPDATE projects SET status='applied'")
        worker.process_one(main)
        self.assertEqual(self.operation(restore)["state"], "succeeded")
        with self.connect() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT project_id::text FROM projects WHERE name='demo'"
                ).fetchone()[0],
                self.identity,
            )

    def test_purge_waits_for_both_erasure_receipts(self):
        identity = self.start("purge")
        worker.process_one(main)
        worker.process_one(main)
        worker.process_one(main)
        self.assertEqual(self.operation(identity)["state"], "blocked")
        operation = self.operation(identity)
        payload = {
            key: operation[key] for key in ("operation_id", "project_id", "project")
        }
        payload["verified"] = True
        erasure.atomic(erasure.directory() / (identity + ".receipt.json"), payload)
        worker.process_one(main)
        self.assertEqual(self.operation(identity)["step"], "catalog_removed")
        self.assertNotEqual(self.operation(identity)["state"], "succeeded")
        with self.connect() as conn:
            self.assertIsNone(
                conn.execute("SELECT 1 FROM projects WHERE name='demo'").fetchone()
            )
        erasure.atomic(erasure.directory() / (identity + ".final.json"), payload)
        worker.process_one(main)
        self.assertEqual(self.operation(identity)["state"], "succeeded")

    def test_failed_restore_can_be_retried_with_current_operation_version(self):
        self.start("retire")
        worker.process_one(main)
        identity = self.start("restore")
        worker.process_one(main)
        previous = self.operation(identity)["result"]["deployment_operation_id"]
        with self.connect() as conn:
            conn.execute("UPDATE application_operations SET state='failed'")
        worker.process_one(main)
        operation = self.operation(identity)
        self.assertEqual(operation["state"], "blocked")
        stale = self.client.post(
            "/v1/operations/" + identity + "/retry", headers={"If-Match": "stale"}
        )
        self.assertEqual(stale.status_code, 412)
        response = self.client.post(
            "/v1/operations/" + identity + "/retry",
            headers={"If-Match": operation["updated_at"].isoformat()},
        )
        self.assertEqual(response.status_code, 202, response.text)
        worker.process_one(main)
        result = self.operation(identity)["result"]
        self.assertTrue(result["prepared"])
        self.assertNotEqual(result["deployment_operation_id"], previous)
