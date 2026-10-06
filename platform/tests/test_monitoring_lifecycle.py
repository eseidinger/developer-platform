"""Exercise API authorization and catalog/discovery ordering without a live installation."""
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from kubernetes.client.exceptions import ApiException
from app import main
from app.identity import AuthenticationError, Principal


class Catalog:
    def __init__(self):
        self.rows = {}
        self.project_ids = {}
        self.environment_ids = {}
        self.application_ids = {}
        self.revisions = {}
        self.operations = {}
        self.result = []
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    @contextmanager
    def transaction(self):
        self.events.append("transaction.begin")
        try:
            yield
        except Exception:
            self.events.append("transaction.rollback")
            raise
        else:
            self.events.append("transaction.commit")

    def execute(self, query, params=()):
        self.events.append(query)
        if query.startswith("INSERT INTO projects"):
            if "NULL, 'empty'" in query:
                name = params[0]
                self.rows[name] = (None, "empty")
                self.project_ids.setdefault(name, "project-id-" + name)
                self.result = [(name, "empty", datetime(2026, 10, 4, tzinfo=timezone.utc))]
            else:
                name, spec = params
                self.rows[name] = (spec.obj, "provisioning")
                project_id = self.project_ids.setdefault(name, "project-id-" + name)
                self.result = [(project_id,)]
        elif query.startswith("UPDATE projects SET status="):
            status = query.split("status='")[1].split("'")[0]
            self.rows[params[0]] = (self.rows[params[0]][0], status)
        elif query.startswith("INSERT INTO project_environments"):
            project_id, name = params
            key = (project_id, name)
            self.result = [(self.environment_ids.setdefault(key, "environment-" + project_id),)]
        elif query.startswith("INSERT INTO project_applications"):
            environment_id, name = params
            key = (environment_id, name)
            self.result = [(self.application_ids.setdefault(key, "application-" + name),)]
        elif query.startswith("SELECT revision, spec FROM application_revisions"):
            application_id = params[0]
            revisions = self.revisions.get(application_id, [])
            self.result = [(revisions[-1][0], revisions[-1][1])] if revisions else []
        elif query.startswith("INSERT INTO application_revisions"):
            application_id, revision, spec = params
            self.revisions.setdefault(application_id, []).append((revision, spec.obj))
        elif query.startswith("SELECT operation_id, state FROM application_operations"):
            application_id, revision, operation_kind = params
            pending = [(operation_id, operation) for operation_id, operation in self.operations.items()
                       if operation["application_id"] == application_id
                       and operation["revision"] == revision
                       and operation["operation_kind"] == operation_kind
                       and operation["state"] in {"queued", "running"}]
            self.result = [(pending[-1][0], pending[-1][1]["state"])] if pending else []
        elif query.startswith("SELECT 1") and "FROM application_operations" in query:
            project_name = params[0]
            active = any(operation["project_name"] == project_name
                         and operation["state"] in {"queued", "running"}
                         for operation in self.operations.values())
            self.result = [(1,)] if active else []
        elif query.startswith("INSERT INTO application_operations"):
            (application_id, revision, operation_kind, state, actor_issuer, actor_subject,
             envelope_version, envelope) = params
            operation_id = str(uuid4())
            application_key = next(key for key, app_id in self.application_ids.items()
                                   if app_id == application_id)
            self.operations[operation_id] = {
                "application_id": application_id, "revision": revision, "operation_kind": operation_kind,
                "state": state, "envelope_version": envelope_version, "envelope": envelope.obj,
                "actor_issuer": actor_issuer, "actor_subject": actor_subject,
                "project_name": application_key[1], "result_version": None, "result": None, "error_code": None,
            }
            self.result = [(operation_id,)]
        elif "FROM application_operations" in query:
            operation_id = str(params[0])
            operation = self.operations.get(operation_id)
            revision_specs = self.revisions.get(operation["application_id"], []) if operation else []
            spec = next((spec for revision, spec in revision_specs
                         if revision == operation["revision"]), None)
            self.result = [(
                operation_id, operation["revision"], operation["state"], operation["result_version"],
                operation["result"], operation["error_code"], operation["project_name"], spec,
            )] if operation else []
        elif query.startswith("SELECT p.project_id, p.status"):
            name = params[0]
            application_id = "application-" + name
            revisions = self.revisions.get(application_id, [])
            self.result = [(self.project_ids[name], self.rows[name][1], application_id,
                            revisions[-1][0], revisions[-1][1])] if name in self.rows and revisions else []
        elif query.startswith("SELECT r.spec, p.status FROM projects"):
            name, target = params
            spec = next((spec for revision, spec in self.revisions.get("application-" + name, [])
                         if revision == target), None)
            self.result = [(spec, self.rows[name][1])] if spec is not None and name in self.rows else []
        elif query.startswith("SELECT r.revision, r.created_at, r.spec"):
            self.result = [(revision, datetime(2026, 10, 3, tzinfo=timezone.utc), spec)
                           for revision, spec in reversed(self.revisions.get("application-" + params[0], []))]
        elif query.startswith("SELECT max(r.revision), (array_agg"):
            revisions = self.revisions.get("application-" + params[0], [])
            status = self.rows[params[0]][1] if params[0] in self.rows else None
            self.result = ([(revisions[-1][0], revisions[-1][1], status)] if revisions else
                           ([(None, None, status)] if params[0] in self.rows else []))
        elif query.startswith("SELECT max(r.revision)"):
            revisions = self.revisions.get("application-" + params[0], [])
            self.result = [(revisions[-1][0] if revisions else None,)]
        elif query.startswith("SELECT name, spec, status"):
            self.result = [(name, *row) for name, row in self.rows.items()]
        elif query.startswith("SELECT status FROM"):
            row = self.rows.get(params[0])
            self.result = [(row[1],)] if row else []
        elif query.startswith("SELECT 1 FROM projects"):
            self.result = [(1,)] if params[0] in self.rows else []
        elif query.startswith("SELECT role, count(*) FROM platform_grants"):
            self.result = [("developer", 1)]
        elif query.startswith("SELECT status, count(*) FROM deployment_credentials"):
            self.result = [("active", 1)]
        elif "FROM deployment_credentials WHERE issuer=" in query:
            self.result = []
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
        self.digest = "sha256:" + "a" * 64
        resolver = patch.object(main, "resolve_image", side_effect=lambda image: image.split(":")[0] + "@" + self.digest)
        self.resolver = resolver.start()
        self.addCleanup(resolver.stop)
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

    def complete_operations(self):
        for operation in self.catalog.operations.values():
            operation["state"] = "succeeded"

    def test_repeated_queued_deploy_reuses_operation_without_provider_side_effects(self):
        first = self.deploy()
        self.assertEqual(first.status_code, 202)
        second = self.deploy()
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["operation_id"], second.json()["operation_id"])
        app_id = next(iter(self.catalog.application_ids.values()))
        self.assertEqual([revision for revision, _ in self.catalog.revisions[app_id]], [1])
        self.assertEqual(len(self.catalog.operations), 1)
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()

    def rollback(self, revision, **headers):
        return self.client.post("/projects/smoke/rollback", json={"revision": revision},
                                headers=dict(self.headers, **headers))

    def test_rollback_reapplies_a_retained_spec_as_a_new_revision(self):
        self.deploy()
        self.spec["image"] = "example:v2"
        self.deploy()
        self.complete_operations()

        listing = self.client.get("/projects/smoke/revisions", headers=self.headers).json()
        self.assertEqual(listing["current_revision"], 2)
        self.assertEqual([(r["revision"], r["current"]) for r in listing["revisions"]],
                         [(2, True), (1, False)])
        self.assertEqual(listing["revisions"][1]["image"], "example@" + self.digest)

        response = self.rollback(1, **{"If-Match": "2"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["revision"], 3)
        app_id = next(iter(self.catalog.application_ids.values()))
        self.assertEqual(self.catalog.revisions[app_id][2][1], self.catalog.revisions[app_id][0][1])
        self.assertEqual(self.catalog.rows["smoke"][0], self.catalog.revisions[app_id][0][1])
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()

    def test_rollback_to_a_revision_without_resources_is_listed_and_reapplied(self):
        self.deploy()
        app_id = next(iter(self.catalog.application_ids.values()))
        legacy = {k: v for k, v in self.catalog.revisions[app_id][0][1].items() if k != "resources"}
        self.catalog.revisions[app_id][0] = (1, legacy)
        self.spec["image"] = "example:v2"
        self.deploy()
        self.complete_operations()

        listing = self.client.get("/projects/smoke/revisions", headers=self.headers).json()
        self.assertIsNone(listing["revisions"][1]["resources"])
        response = self.rollback(1)
        self.assertEqual((response.status_code, response.json()["revision"]), (202, 3))
        self.assertEqual(self.catalog.revisions[app_id][2][1], legacy)

    def test_rollback_rejects_unknown_revisions_stale_if_match_and_retired_projects(self):
        self.deploy()
        self.complete_operations()
        self.assertEqual(self.rollback(9).status_code, 404)
        self.assertEqual(self.rollback(1, **{"If-Match": "5"}).json()["code"], "revision_conflict")
        self.assertEqual(self.rollback(1, **{"If-Match": "x"}).status_code, 400)
        self.catalog.rows["smoke"] = (self.catalog.rows["smoke"][0], "retired")
        self.assertEqual(self.rollback(1).status_code, 409)
        self.assertEqual(self.client.post("/projects/smoke/rollback", json={"revision": 0},
                                          headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get("/projects/none/revisions", headers=self.headers).status_code, 404)

    def test_resource_usage_requires_view_grant_labels_state_and_is_audited(self):
        self.deploy()
        self.complete_operations()
        usage = {"state": "missing", "reason": "NoMetricsForProject", "pods": [], "totals": None}
        with patch.object(main, "observe_usage", return_value=usage) as observe:
            response = self.client.get("/projects/smoke/resource-usage", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"project": "smoke", **usage})
            observe.assert_called_once_with(self.runtime, "smoke", main.log)
            self.assertEqual(self.mocks[4].call_args.args[1:], (self.principal, "view", "smoke"))
            self.assertEqual(self.client.get("/projects/none/resource-usage", headers=self.headers).status_code, 404)
            self.mocks[4].return_value = False
            self.assertEqual(self.client.get("/projects/smoke/resource-usage", headers=self.headers).status_code, 403)
        actions = [call.args[1] for call in self.mocks[3].call_args_list]
        self.assertIn("project.usage.inspect", actions)

    def test_logs_require_view_grant_validate_limits_and_are_audited(self):
        self.deploy()
        self.complete_operations()
        logs = {"state": "no_pods", "reason": "NoPodsForProject", "lines": [], "truncated": False}
        with patch.object(main, "observe_logs", return_value=logs) as observe:
            response = self.client.get("/projects/smoke/logs?tail=50&since_seconds=60", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"project": "smoke", **logs})
            observe.assert_called_once_with(self.runtime, "smoke", main.log, 50, 60,
                                            instance=None, search=None, after=None, before=None)
            self.assertEqual(self.mocks[4].call_args.args[1:], (self.principal, "view", "smoke"))
            for query in ("tail=0", "tail=1001", "since_seconds=0", "since_seconds=86401"):
                self.assertEqual(self.client.get("/projects/smoke/logs?" + query, headers=self.headers).status_code, 422)
            self.assertEqual(self.client.get("/projects/none/logs", headers=self.headers).status_code, 404)
            self.mocks[4].return_value = False
            self.assertEqual(self.client.get("/projects/smoke/logs", headers=self.headers).status_code, 403)
        self.assertEqual(observe.call_count, 1)
        actions = [call.args[1] for call in self.mocks[3].call_args_list]
        self.assertIn("project.logs.read", actions)

    def test_if_match_makes_updates_conditional_on_the_current_revision(self):
        def put(value=None):
            headers = dict(self.headers, **({"If-Match": value} if value is not None else {}))
            return self.client.put("/projects/smoke", json=self.spec, headers=headers)

        self.assertEqual(put("1").status_code, 409)
        self.assertEqual(put("0").status_code, 202)
        self.spec["image"] = "example:v2"
        stale = put("0")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "revision_conflict")
        self.assertEqual(stale.json()["current_revision"], 1)
        app_id = next(iter(self.catalog.application_ids.values()))
        self.assertEqual([revision for revision, _ in self.catalog.revisions[app_id]], [1])
        self.assertEqual(self.catalog.rows["smoke"][0]["image"], "example:v1")
        self.assertEqual(put('"1"').json()["revision"], 2)
        self.spec["image"] = "example:v3"
        self.assertEqual(put().json()["revision"], 3)
        self.assertEqual(put("abc").status_code, 400)
        self.assertEqual(put("-1").status_code, 400)

    def test_drift_is_reported_and_audited_without_changing_the_cluster(self):
        self.assertEqual(self.client.get("/projects/smoke/drift", headers=self.headers).status_code, 404)
        self.deploy()
        drifted = {"state": "drifted", "differences": [{"field": "replicas", "desired": 1, "observed": 3}]}
        with patch.object(main, "observe_drift", return_value=drifted) as observe:
            response = self.client.get("/projects/smoke/drift", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"project": "smoke", "revision": 1, **drifted})
        self.assertEqual(observe.call_args.args[1], "smoke")
        actions = [call.args[1] for call in self.mocks[3].call_args_list]
        self.assertIn("project.drift.detected", actions)
        self.mocks[-1].assert_not_called()
        self.runtime.resources.get.return_value.patch.assert_not_called()

    def test_changed_spec_adds_immutable_revision_and_keeps_identity(self):
        self.assertEqual(self.deploy().status_code, 202)
        project_id = self.catalog.project_ids["smoke"]
        environment_id = next(iter(self.catalog.environment_ids.values()))
        app_id = next(iter(self.catalog.application_ids.values()))
        self.spec["image"] = "example:v2"
        self.assertEqual(self.deploy().status_code, 202)
        self.assertEqual(self.catalog.project_ids["smoke"], project_id)
        self.assertEqual(next(iter(self.catalog.environment_ids.values())), environment_id)
        self.assertEqual(next(iter(self.catalog.application_ids.values())), app_id)
        revisions = self.catalog.revisions[app_id]
        self.assertEqual([revision for revision, _ in revisions], [1, 2])
        self.assertEqual([spec["image"] for _, spec in revisions], ["example:v1", "example:v2"])

    def test_deploy_persists_revision_and_versioned_operation_before_returning_accepted(self):
        response = self.deploy()

        self.assertEqual(response.status_code, 202)
        body = response.json()
        operation_id = body["operation_id"]
        self.assertEqual(body["status_url"], f"/v1/operations/{operation_id}")
        operation = self.catalog.operations[operation_id]
        self.assertEqual(operation["state"], "queued")
        self.assertEqual(operation["envelope_version"], 1)
        self.assertEqual(operation["envelope"]["spec"],
                         {**self.spec, "port": 8080, "resolved_image": "example@" + self.digest})
        committed_at = self.catalog.events.index("transaction.commit")
        revision_insert = next(index for index, event in enumerate(self.catalog.events)
                               if event.startswith("INSERT INTO application_revisions"))
        operation_insert = next(index for index, event in enumerate(self.catalog.events)
                                if event.startswith("INSERT INTO application_operations"))
        self.assertLess(revision_insert, committed_at)
        self.assertLess(operation_insert, committed_at)
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()

    def test_operation_progress_uses_current_project_view_grant(self):
        self.assertEqual(self.deploy().status_code, 202)
        operation_id = next(iter(self.catalog.operations))
        self.catalog.operations[operation_id]["state"] = "succeeded"
        self.catalog.operations[operation_id]["result_version"] = 1
        self.catalog.operations[operation_id]["result"] = {"api_token": "must-not-be-returned"}

        readiness = {
            "state": "ready",
            "desired_replicas": 1,
            "ready_replicas": 1,
            "desired_image": "example:v1",
            "deployment_image": "example:v1",
            "active_images": ["example:v1"],
            "active_image_ids": ["docker-pullable://example@sha256:abc"],
            "reason": None,
            "observed_at": "2026-10-03T00:00:00+00:00",
        }
        with patch.object(main, "observe_deployment", return_value=readiness) as observe:
            response = self.client.get(f"/v1/operations/{operation_id}", headers=self.headers)
            self.mocks[4].return_value = False
            revoked_response = self.client.get(f"/v1/operations/{operation_id}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["operation_id"], operation_id)
        self.assertEqual(response.json()["state"], "succeeded")
        self.assertEqual(response.json()["result"], {"api_token": "[REDACTED]"})
        self.assertEqual(response.json()["readiness"], readiness)
        observe.assert_called_once_with(self.runtime, "smoke", "example@" + self.digest, main.log)
        self.assertEqual(self.mocks[4].call_args.args[1:], (self.principal, "view", "smoke"))
        self.assertEqual(revoked_response.status_code, 403)
        observe.assert_called_once()
        self.assertEqual(self.mocks[3].call_args.args[1:5],
                         ("authorization", "project", "smoke", "denied"))

    def restart(self):
        return self.client.post("/projects/smoke/restart", headers=self.headers)

    def deploy_applied(self):
        self.assertEqual(self.deploy().status_code, 202)
        self.complete_operations()
        self.catalog.rows["smoke"] = (self.catalog.rows["smoke"][0], "applied")

    def test_restart_accepts_an_operation_on_the_current_revision_without_provider_side_effects(self):
        self.deploy_applied()
        self.catalog.operations.clear()

        first = self.restart()
        second = self.restart()

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.json()["operation_id"], first.json()["operation_id"])
        self.assertEqual(first.json()["revision"], 1)
        self.assertEqual(first.json()["status_url"], "/v1/operations/" + first.json()["operation_id"])
        operation = self.catalog.operations[first.json()["operation_id"]]
        self.assertEqual(len(self.catalog.operations), 1)
        self.assertEqual(operation["operation_kind"], "restart")
        self.assertEqual(operation["state"], "queued")
        self.assertEqual(operation["actor_subject"], "person-1")
        self.assertEqual(operation["envelope"]["spec"], self.catalog.rows["smoke"][0])
        self.assertEqual(self.catalog.rows["smoke"][1], "applied")
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()
        self.assertEqual(self.mocks[3].call_args.args[1:5], ("project.restart", "project", "smoke", "succeeded"))

    def test_restart_requires_change_grant_and_an_applied_project(self):
        self.assertEqual(self.restart().status_code, 404)
        self.assertEqual(self.deploy().status_code, 202)
        self.assertEqual(self.restart().status_code, 409)
        self.complete_operations()
        self.catalog.rows["smoke"] = (self.catalog.rows["smoke"][0], "applied")
        self.catalog.operations.clear()
        self.mocks[4].return_value = False
        self.assertEqual(self.restart().status_code, 403)
        self.assertEqual(self.catalog.operations, {})
        self.assertEqual(self.mocks[4].call_args.args[1:], (self.principal, "change", "smoke"))

    def test_retirement_is_blocked_while_an_operation_is_active(self):
        self.assertEqual(self.deploy().status_code, 202)
        self.assertEqual(self.retire().status_code, 409)
        self.runtime.resources.get.assert_not_called()

    def test_retire_requires_auth_confirmation_and_absent_namespace(self):
        self.deploy()
        self.complete_operations()
        self.assertIn(self.retire(headers={}).status_code, (401, 403))
        self.mocks[5].verify.side_effect = AuthenticationError()
        self.assertEqual(self.retire(headers={"Authorization": "Bearer wrong"}).status_code, 401)
        self.mocks[5].verify.side_effect = None
        self.assertEqual(self.retire(confirmation="different").status_code, 400)
        self.assertEqual(self.retire().status_code, 409)
        self.runtime.resources.get.return_value.get.side_effect = ApiException(status=403)
        self.assertEqual(self.retire().status_code, 503)
        self.assertFalse((Path(self.directory.name) / "applications.json").exists())
        self.assertEqual(self.catalog.rows["smoke"][1], "provisioning")

    def test_retirement_retry_and_redeployment(self):
        self.deploy()
        self.complete_operations()
        self.runtime.resources.get.return_value.get.side_effect = ApiException(status=404)
        response = self.retire()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data_retained"])
        self.assertEqual(self.targets(), [])
        self.assertIn("smoke", self.catalog.rows)
        self.assertEqual(self.retire().status_code, 200)
        self.assertEqual(self.deploy().status_code, 202)
        self.assertEqual(self.targets(), [])

    def preview(self):
        return self.client.get("/projects/smoke/retirement-preview", headers=self.headers)

    def confirmed_retire(self, token):
        return self.client.post("/projects/smoke/retire", headers=self.headers,
                                json={"confirm_name": "smoke", "scope_token": token})

    def test_retirement_preview_lists_removed_and_retained_scope(self):
        self.assertEqual(self.preview().status_code, 404)
        self.deploy()
        blocked = self.preview().json()
        self.assertEqual(blocked["blockers"], ["active_operation"])
        self.complete_operations()
        body = self.preview().json()
        self.assertEqual(body["blockers"], [])
        self.assertEqual(body["route"], "smoke.apps.localhost")
        kinds = {(item["kind"], item["name"]) for item in body["removes"]}
        self.assertTrue({("Namespace", "project-smoke"), ("Deployment", "smoke"), ("Ingress", "smoke"),
                         ("Secret", "database")} <= kinds)
        self.assertEqual(body["retains"]["database"], "project_smoke")
        self.assertEqual(body["access"], {"grants_by_role": {"developer": 1},
                                           "credentials_by_status": {"active": 1}})
        self.assertNotIn("PGPASSWORD", json.dumps(body))
        self.assertEqual(self.preview().json()["scope_token"], body["scope_token"])

    def test_confirmed_retirement_deletes_namespace_waits_for_termination_and_records_inventory(self):
        self.deploy()
        self.complete_operations()
        token = self.preview().json()["scope_token"]
        namespaces = self.runtime.resources.get.return_value
        namespaces.get.return_value = object()
        pending = self.confirmed_retire(token)
        self.assertEqual(pending.status_code, 202)
        self.assertEqual(pending.json()["status"], "retiring")
        namespaces.delete.assert_called_with(name="project-smoke")
        self.assertNotEqual(self.catalog.rows["smoke"][1], "retired")
        namespaces.get.side_effect = ApiException(status=404)
        namespaces.delete.side_effect = ApiException(status=404)
        done = self.confirmed_retire(token)
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()["retained"]["database"], "project_smoke")
        self.assertEqual(self.catalog.rows["smoke"][1], "retired")
        self.assertTrue(any(isinstance(e, str) and e.startswith("INSERT INTO project_retirements")
                            for e in self.catalog.events))
        self.assertTrue(any(isinstance(e, str) and e.startswith("DELETE FROM platform_grants")
                            for e in self.catalog.events))
        self.assertTrue(any(isinstance(e, str) and e.startswith("UPDATE deployment_credentials SET status='revocation_pending'")
                            for e in self.catalog.events))
        self.assertEqual(self.targets(), [])
        actions = [call.args[1] for call in self.mocks[3].call_args_list]
        self.assertIn("project.retire.requested", actions)
        self.assertEqual(actions.count("project.retire"), 1)

    def test_changed_scope_invalidates_the_token_without_deleting_anything(self):
        self.deploy()
        self.complete_operations()
        token = self.preview().json()["scope_token"]
        self.spec["image"] = "example:v2"
        self.deploy()
        self.complete_operations()
        response = self.confirmed_retire(token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "scope_changed")
        self.runtime.resources.get.return_value.delete.assert_not_called()
        self.assertEqual(self.confirmed_retire("0" * 32).status_code, 409)
        self.assertEqual(self.catalog.rows["smoke"][1], "provisioning")

    def test_confirmed_retirement_failure_is_retryable_and_keeps_the_project(self):
        self.deploy()
        self.complete_operations()
        token = self.preview().json()["scope_token"]
        namespaces = self.runtime.resources.get.return_value
        namespaces.delete.side_effect = ApiException(status=500)
        self.assertEqual(self.confirmed_retire(token).status_code, 503)
        self.assertNotEqual(self.catalog.rows["smoke"][1], "retired")
        namespaces.delete.side_effect = None
        namespaces.get.side_effect = ApiException(status=404)
        self.assertEqual(self.confirmed_retire(token).status_code, 200)

    def test_retirement_publish_failure_reconciles_from_durable_status(self):
        self.deploy()
        self.complete_operations()
        self.runtime.resources.get.return_value.get.side_effect = ApiException(status=404)
        with patch.object(main, "publish_catalog", side_effect=OSError):
            self.assertEqual(self.retire().status_code, 503)
        self.assertEqual(self.catalog.rows["smoke"][1], "retired")
        main.publish_catalog(self.catalog)
        self.assertEqual(self.targets(), [])

    def test_invalid_profile_rejected_before_catalog_mutation(self):
        self.spec["probe_profile"] = "arbitrary"
        self.assertEqual(self.deploy().status_code, 422)
        self.assertEqual(self.catalog.rows, {})
        rejected = self.mocks[3].call_args
        self.assertEqual(rejected.args[1:5], ("request.validation", "platform-api", "smoke", "rejected"))

    def test_versioned_envelope_is_accepted_and_shares_revisions_with_the_flat_body(self):
        envelope = {"apiVersion": "platform.example/v1alpha1", "kind": "Application",
                    "metadata": {"name": "smoke"},
                    "spec": {"application": {"runtime": {"type": "container", "image": "example:v1"}}}}
        first = self.client.put("/projects/smoke", json=envelope, headers=self.headers)
        self.assertEqual(first.status_code, 202)
        stored = self.catalog.rows["smoke"][0]
        self.assertEqual((stored["image"], stored["port"], stored["probe_profile"]), ("example:v1", 8080, "status"))
        self.complete_operations()
        flat = self.client.put("/projects/smoke", json={"name": "smoke", "image": "example:v1"}, headers=self.headers)
        self.assertEqual(flat.json()["revision"], first.json()["revision"])

    def test_invalid_envelopes_are_rejected_and_audited_before_catalog_mutation(self):
        base = {"apiVersion": "platform.example/v1alpha1", "kind": "Application", "metadata": {"name": "smoke"},
                "spec": {"application": {"runtime": {"type": "container", "image": "example:v1"}}}}
        for label, body in (
                ("version", {**base, "apiVersion": "platform.example/v9"}),
                ("project", {**base, "metadata": {"name": "smoke", "project": "other"}}),
                ("scaling", {**base, "spec": {"application": {**base["spec"]["application"],
                                                               "scaling": {"minInstances": 1, "maxInstances": 2}}}}),
                ("resources", {**base, "spec": {"application": {**base["spec"]["application"],
                                                                 "resources": {"limits": {"cpu": "9"}}}}})):
            with self.subTest(label):
                self.assertEqual(self.client.put("/projects/smoke", json=body, headers=self.headers).status_code, 422)
                self.assertEqual(self.mocks[3].call_args.args[1:5],
                                 ("request.validation", "platform-api", "smoke", "rejected"))
        self.assertEqual(self.catalog.rows, {})

    def test_rejections_carry_stable_codes_and_capabilities_are_published(self):
        base = {"apiVersion": "platform.example/v1alpha1", "kind": "Application", "metadata": {"name": "smoke"},
                "spec": {"application": {"runtime": {"type": "container", "image": "example:v1"}}}}
        scaled = {**base, "spec": {"application": {**base["spec"]["application"],
                                                    "scaling": {"minInstances": 1, "maxInstances": 3}}}}
        cases = ((scaled, "unsupported_capability"),
                 ({**base, "spec": {**base["spec"], "configuration": {"secrets": {}}}}, "unsupported_capability"),
                 ({**base, "apiVersion": "platform.example/v9"}, "invalid_spec"),
                 ({**self.spec, "scaling": 2}, "unsupported_capability"),
                 ({**self.spec, "probe_profile": "arbitrary"}, "invalid_spec"),
                 ({**self.spec, "port": 80}, "invalid_spec"))
        for body, code in cases:
            with self.subTest(body=body):
                response = self.client.put("/projects/smoke", json=body, headers=self.headers)
                self.assertEqual((response.status_code, response.json()["code"]), (422, code))
        listed = self.client.get("/v1/capabilities", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertFalse(listed.json()["environments"]["default"]["scaling"]["autoscaling"])
        self.assertTrue(listed.json()["environments"]["default"]["configuration"]["secrets"])
        self.assertIn("docker.io", listed.json()["imageRegistries"])
        self.mocks[5].verify.side_effect = AuthenticationError()
        self.assertEqual(self.client.get("/v1/capabilities", headers=self.headers).status_code, 401)

    def test_configuration_is_a_validated_revision_with_activation(self):
        self.assertEqual(self.deploy().status_code, 202)
        path = "/projects/smoke/configuration"
        for values in ({"PGHOST": "x"}, {"DB_PASSWORD": "x"}, {"1A": "x"}, {"A": 1}, {"A": "x" * 1025},
                       {"A": "-----BEGIN KEY-----"}):
            with self.subTest(values=values):
                response = self.client.put(path, json={"values": values}, headers=self.headers)
                self.assertEqual((response.status_code, response.json()["code"]), (422, "invalid_configuration"))
        self.assertEqual(len(self.catalog.revisions["application-smoke"]), 1)
        self.assertEqual(self.client.put(path, json={"values": {"MODE": "fast"}},
                                         headers={**self.headers, "If-Match": "5"}).status_code, 409)
        changed = self.client.put(path, json={"values": {"MODE": "fast"}}, headers=self.headers)
        self.assertEqual((changed.status_code, changed.json()["revision"], changed.json()["rollout_required"]),
                         (202, 2, True))
        self.assertEqual(self.catalog.revisions["application-smoke"][-1][1]["configuration"], {"MODE": "fast"})
        audited = [c.args for c in self.mocks[3].call_args_list if c.args[1] == "project.configuration.update"]
        self.assertNotIn("fast", json.dumps(audited, default=str))
        self.runtime.resources.get.return_value.get.return_value = {
            "spec": {"replicas": 1, "template": {"spec": {"containers": [{"env": []}]}}}, "status": {}}
        shown = self.client.get(path, headers=self.headers).json()
        self.assertEqual((shown["values"], shown["revision"], shown["activation"]["state"]),
                         ({"MODE": "fast"}, 2, "pending"))
        self.runtime.resources.get.return_value.get.return_value = {
            "spec": {"replicas": 1, "template": {"spec": {"containers": [
                {"env": [{"name": "MODE", "value": "fast"}]}]}}},
            "status": {"updatedReplicas": 1, "readyReplicas": 1, "replicas": 1}}
        self.assertEqual(self.client.get(path, headers=self.headers).json()["activation"]["state"], "active")
        removed = self.client.put(path, json={"values": {}}, headers=self.headers)
        self.assertEqual(removed.json()["revision"], 3)
        self.assertNotIn("configuration", self.catalog.revisions["application-smoke"][-1][1])
        self.mocks[4].return_value = False
        self.assertEqual(self.client.get(path, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.put(path, json={"values": {}}, headers=self.headers).status_code, 403)

    def test_component_deployment_preserves_separately_managed_configuration(self):
        self.assertEqual(self.deploy().status_code, 202)
        configured = self.client.put("/projects/smoke/configuration", json={"values": {"MODE": "fast"}},
                                     headers=self.headers)
        self.assertEqual(configured.status_code, 202)
        component_body = {
            "apiVersion": "platform.example/v1alpha2", "kind": "Application",
            "metadata": {"name": "smoke"},
            "spec": {"components": [{
                "name": "api", "type": "service",
                "runtime": {"type": "container", "image": "example:v2"},
                "ports": [{"name": "http", "protocol": "http", "port": 8080}],
            }]},
        }
        migrated = self.client.put("/projects/smoke", json=component_body, headers=self.headers)
        self.assertEqual(migrated.status_code, 202)
        self.assertEqual(self.catalog.revisions["application-smoke"][-1][1]["configuration"], {"MODE": "fast"})

    def test_secrets_are_write_only_audited_by_name_and_roll_the_pods(self):
        from test_secrets import cluster
        fake = cluster()
        self.runtime.resources = fake.resources
        self.assertEqual(self.deploy().status_code, 202)
        base = "/projects/smoke/secrets"
        value = "hunter2-very-secret"
        for name, body in (("PGHOST", {"value": "x"}), ("1A", {"value": "x"}), ("API_KEY", {"value": ""}),
                           ("API_KEY", {"value": 5}), ("API_KEY", {"value": "x", "other": 1}), ("API_KEY", {})):
            with self.subTest(name=name, body=body):
                response = self.client.put(f"{base}/{name}", json=body, headers=self.headers)
                self.assertEqual((response.status_code, response.json()["code"]), (422, "invalid_secret"))
        self.assertIsNone(fake.secret)
        response = self.client.put(f"{base}/DB_PASSWORD", json={"value": value}, headers=self.headers)
        self.assertEqual((response.status_code, response.json()["rollout_required"],
                          response.json()["rotated"]), (202, True, False))
        self.assertEqual(self.client.put(f"{base}/DB_PASSWORD", json={"value": value + "2"},
                                         headers=self.headers).json()["rotated"], True)
        listed = self.client.get(base, headers=self.headers)
        self.assertEqual([s["name"] for s in listed.json()["secrets"]], ["DB_PASSWORD"])
        self.assertEqual(listed.json()["activation"]["state"], "active")
        everything = listed.text + json.dumps([c.args for c in self.mocks[3].call_args_list], default=str)
        self.assertNotIn(value, everything)
        self.assertTrue(any(c.args[1] == "project.secret.set" for c in self.mocks[3].call_args_list))
        self.assertEqual((listed.json()["secrets"][0]["version"], listed.json()["secrets"][0]["state"]), (2, "rotating"))
        confirm = f"{base}/DB_PASSWORD/confirm"
        fake.deployment["status"]["updatedReplicas"] = 0
        self.assertEqual(self.client.post(confirm, headers=self.headers).json()["code"], "not_adopted")
        fake.deployment["status"]["updatedReplicas"] = 1
        self.assertEqual(self.client.post(confirm, headers=self.headers).json()["state"], "active")
        self.assertEqual(self.client.post(confirm, headers=self.headers).json()["code"], "no_previous_version")
        self.assertEqual(self.client.post(f"{base}/DB_PASSWORD/revert", headers=self.headers).json()["code"],
                         "no_previous_version")
        self.client.put(f"{base}/DB_PASSWORD", json={"value": value + "3"}, headers=self.headers)
        reverted = self.client.post(f"{base}/DB_PASSWORD/revert", headers=self.headers)
        self.assertEqual((reverted.status_code, fake.secret["data"]["DB_PASSWORD"]), (202, value + "2"))
        self.assertEqual(self.client.post(f"{base}/MISSING/confirm", headers=self.headers).status_code, 404)
        configured = self.client.put("/projects/smoke/configuration", json={"values": {"DB_PASSWORD": "x"}},
                                     headers=self.headers)
        self.assertEqual(configured.status_code, 422)
        self.client.put("/projects/smoke/configuration", json={"values": {"MODE": "a"}}, headers=self.headers)
        self.assertEqual(self.client.put(f"{base}/MODE", json={"value": "x"}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.delete(f"{base}/MISSING", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.delete(f"{base}/DB_PASSWORD", headers=self.headers).status_code, 202)
        self.assertEqual(self.client.get(base, headers=self.headers).json()["secrets"], [])
        self.assertEqual(self.client.get("/projects/other/secrets", headers=self.headers).status_code, 404)
        self.mocks[4].return_value = False
        self.assertEqual(self.client.get(base, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.put(f"{base}/A", json={"value": "x"}, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.delete(f"{base}/A", headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(f"{base}/A/confirm", headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(f"{base}/A/revert", headers=self.headers).status_code, 403)

    def test_unknown_project_field_rejected_before_catalog_mutation(self):
        self.spec["unexpected"] = "must not be ignored"

        response = self.deploy()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.catalog.rows, {})
        self.assertEqual(self.catalog.revisions, {})
        self.assertEqual(self.catalog.operations, {})
        rejected = self.mocks[3].call_args
        self.assertEqual(rejected.args[1:5], ("request.validation", "platform-api", "smoke", "rejected"))
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()

    def test_unsupported_capabilities_are_rejected_before_any_side_effect(self):
        unsupported = {
            "scaling": {"min": 1, "max": 3},
            "object_storage": {"bucket": "assets"},
            "messaging": {"queue": "jobs"},
            "cache": {"size": "1Gi"},
            "components": [{"image": "other"}],
            "resources": {"cpu": "4"},
            "environment": {"LOG": "debug"},
        }
        for field, value in unsupported.items():
            with self.subTest(field=field):
                self.spec[field] = value
                self.assertEqual(self.deploy().status_code, 422)
                del self.spec[field]
        self.assertEqual(self.catalog.rows, {})
        self.assertEqual(self.catalog.operations, {})
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()

    def test_accepted_revision_records_the_resolved_digest_reference(self):
        response = self.deploy()

        self.assertEqual(response.status_code, 202)
        stored = self.catalog.rows["smoke"][0]
        self.assertEqual(stored["image"], "example:v1")
        self.assertEqual(stored["resolved_image"], "example@" + self.digest)
        self.assertEqual(self.catalog.operations[response.json()["operation_id"]]["envelope"]["spec"], stored)

    def test_empty_project_accepts_grants_before_its_first_ci_deployment(self):
        with patch.object(main, "require_platform_admin"):
            created = self.client.post("/projects", json={"name": "smoke"}, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["status"], "empty")
        self.assertIsNone(created.json()["spec"])
        granted = self.client.put("/projects/smoke/grants", headers=self.headers, json={
            "issuer": "https://issuer.example", "subject": "project-admin", "role": "project-admin"})
        self.assertEqual(granted.status_code, 200)
        revisions = self.client.get("/projects/smoke/revisions", headers=self.headers)
        self.assertEqual(revisions.json(), {"project": "smoke", "current_revision": None, "revisions": []})
        self.assertEqual(self.client.get("/projects/smoke/logs", headers=self.headers).status_code, 409)

        deployed = self.deploy()
        self.assertEqual(deployed.status_code, 202)
        self.assertEqual(deployed.json()["revision"], 1)
        self.assertEqual(self.catalog.rows["smoke"][1], "provisioning")

    def test_unchanged_tag_digest_reuses_revision_and_moved_tag_creates_one(self):
        first = self.deploy().json()["revision"]
        self.complete_operations()
        self.assertEqual(self.deploy().json()["revision"], first)
        self.complete_operations()
        self.digest = "sha256:" + "b" * 64
        self.assertEqual(self.deploy().json()["revision"], first + 1)

    def test_resources_are_validated_normalized_and_recorded_in_the_revision(self):
        plain = self.deploy().json()["revision"]
        self.assertNotIn("resources", self.catalog.rows["smoke"][0])
        self.complete_operations()
        self.spec = {**self.spec, "resources": {"limits": {"cpu": "1", "memory": "1Gi"}}}
        response = self.deploy()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["revision"], plain + 1)
        self.assertEqual(self.catalog.rows["smoke"][0]["resources"],
                         {"requests": {"cpu": "100m", "memory": "128Mi"},
                          "limits": {"cpu": "1000m", "memory": "1024Mi"}})
        self.complete_operations()
        self.spec = {**self.spec, "resources": {"limits": {"cpu": "1000m", "memory": "1024Mi"}}}
        self.assertEqual(self.deploy().json()["revision"], plain + 1)

    def test_invalid_resources_are_rejected_before_any_side_effect(self):
        before = dict(self.catalog.rows)
        for resources in ({"requests": {"cpu": "2"}}, {"limits": {"memory": "9Gi"}}, {"limits": {"gpu": "1"}},
                          {"requests": {"cpu": "500m"}, "limits": {"cpu": "250m"}}):
            with self.subTest(resources=resources):
                self.spec = {**self.spec, "resources": resources}
                self.assertEqual(self.deploy().status_code, 422)
        self.assertEqual(self.catalog.rows, before)
        self.assertEqual(self.catalog.operations, {})
        self.mocks[-2].assert_not_called()

    def test_resolution_failures_are_rejected_before_any_side_effect(self):
        for reason, status in (("not_found", 422), ("unsupported_registry", 422), ("unavailable", 503)):
            with self.subTest(reason=reason):
                self.resolver.side_effect = main.ImageResolutionError(reason)
                self.assertEqual(self.deploy().status_code, status)
                rejected = self.mocks[3].call_args
                self.assertEqual(rejected.args[1:5], ("project.provision", "project", "smoke", "rejected"))
        self.assertEqual(self.catalog.rows, {})
        self.assertEqual(self.catalog.operations, {})
        self.mocks[-2].assert_not_called()
        self.mocks[-1].assert_not_called()

    def test_mutations_and_authentication_denials_are_audited(self):
        self.assertEqual(self.deploy().status_code, 202)
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

    def test_operator_inspection_and_export_are_platform_admin_only(self):
        self.deploy()
        with patch.object(main, "is_platform_admin", return_value=True), \
             patch.object(main, "grants_for_project", return_value=[
                 ("https://issuer.example", "person-2", "Viewer", "viewer", datetime.now(timezone.utc))
             ]), \
             patch.object(main, "read_events", return_value=[{
                 "id": 9, "occurred_at": "2026-10-02T00:00:00+00:00", "actor_kind": "oidc",
                 "actor_id": "issuer|person-1", "action": "authorization", "target_kind": "project",
                 "target_id": "smoke", "scope": {"project": "smoke"}, "result": "denied",
                 "revision": None, "operation_id": None, "detail": {"reason": "denied"}
             }]):
            permissions = self.client.get("/operator/projects/smoke/permissions", headers=self.headers)
            self.assertEqual(permissions.status_code, 200)
            self.assertEqual(permissions.json()["grants"][0]["role"], "viewer")
            security = self.client.get("/operator/projects/smoke/security-configuration", headers=self.headers)
            self.assertEqual(security.status_code, 200)
            self.assertFalse(security.json()["workload_security"]["service_account_token_automount"])
            exported = self.client.get("/operator/audit/events", headers=self.headers, params={
                "start": "2026-10-02T00:00:00Z", "end": "2026-10-02T01:00:00Z", "format": "csv"})
            self.assertEqual(exported.status_code, 200)
            self.assertIn("occurred_at", exported.text)
            self.assertIn("authorization", exported.text)
        with patch.object(main, "is_platform_admin", return_value=False):
            self.assertEqual(self.client.get("/operator/projects/smoke/permissions", headers=self.headers).status_code, 403)

    def test_audit_export_rejects_unbounded_or_offsetless_windows(self):
        with patch.object(main, "is_platform_admin", return_value=True):
            response = self.client.get("/operator/audit/events", headers=self.headers, params={
                "start": "2026-10-02T00:00:00", "end": "2026-10-02T01:00:00"})
            self.assertEqual(response.status_code, 400)
            response = self.client.get("/operator/audit/events", headers=self.headers, params={
                "start": "2026-10-01T00:00:00Z", "end": "2026-11-02T00:00:01Z"})
            self.assertEqual(response.status_code, 400)


class CrossVersionQueueTests(unittest.TestCase):
    def test_rollback_from_components_requeues_the_retained_legacy_spec(self):
        catalog = Catalog()
        principal = Principal("https://issuer.example", "person-1", "person")
        legacy = {"name": "smoke", "image": "example:v1", "resolved_image": "example@sha256:legacy", "port": 8080}
        components = {"name": "smoke", "components": [
            {"name": "api", "type": "service", "image": "example/api:v1",
             "resolved_image": "example/api@sha256:one", "ports": [{"name": "http", "port": 8080}]},
            {"name": "worker", "type": "scheduled", "image": "example/worker:v1",
             "resolved_image": "example/worker@sha256:two", "schedule": "*/15 * * * *"},
        ]}
        first = main.queue_deploy(catalog, principal, "smoke", legacy, None)
        second = main.queue_deploy(catalog, principal, "smoke", components, None)
        rollback = main.queue_deploy(catalog, principal, "smoke", None, second[2], target=first[2])

        self.assertEqual((first[2], second[2], rollback[2]), (1, 2, 3))
        self.assertEqual(catalog.revisions["application-smoke"][2][1], legacy)
        self.assertEqual(catalog.rows["smoke"][0], legacy)
