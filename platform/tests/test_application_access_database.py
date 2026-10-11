"""Real PostgreSQL lifecycle checks. CI supplies ACCESS_TEST_DSN; no live platform state is used."""
import copy
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx2 as httpx
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main, access_store as store, authorization, access_worker
from app.access_gateway import admitted_identity
from app.access_provider import derived_secret
from app.identity import Principal
from test_application_access import POLICY


@unittest.skipUnless(os.environ.get("ACCESS_TEST_DSN"), "Set ACCESS_TEST_DSN to an isolated PostgreSQL database")
class AccessDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "access_test_" + uuid4().hex
        self.dsn = os.environ["ACCESS_TEST_DSN"]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.connect = lambda: psycopg.connect(self.dsn, autocommit=True, options="-c search_path=" + self.schema)
        with self.connect() as conn:
            conn.execute("CREATE TABLE projects (name text PRIMARY KEY, project_id uuid DEFAULT gen_random_uuid(), status text, spec jsonb)")
            conn.execute("CREATE TABLE project_environments (environment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid, name text)")
            conn.execute("CREATE TABLE project_applications (application_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), environment_id uuid, name text)")
            for project in ("provider", "consumer", "unrelated"):
                conn.execute("INSERT INTO projects(name,status,spec) VALUES (%s,'applied',%s)",
                    (project, Jsonb({"components": [{"name": "api", "type": "service", "exposure": "public", "ports": [{"name": "http", "port": 8080}]}]})))
                conn.execute("INSERT INTO project_environments(project_id,name) SELECT project_id,'default' FROM projects WHERE name=%s", (project,))
                conn.execute("INSERT INTO project_applications(environment_id,name) SELECT environment_id,%s FROM project_environments e JOIN projects p ON p.project_id=e.project_id WHERE p.name=%s", (project, project))
            authorization.initialize(conn)
            store.initialize(conn)
            from app.deployment_credentials import initialize
            initialize(conn)
            self.actor = Principal("https://identity.test/realms/platform", "provider-admin")
            authorization.grant(conn, self.actor, "project", "provider", "project-admin")
            self.consumer = Principal(self.actor.issuer, "consumer-admin")
            authorization.grant(conn, self.consumer, "project", "consumer", "project-admin")
        self.active_actor = self.actor
        main.app.dependency_overrides[main.current_principal] = lambda: self.active_actor
        self.patches = [patch.object(main, "connect", self.connect),
            patch.object(main, "required_audit", Mock()), patch.object(main, "best_effort_audit", Mock()),
            patch.dict(os.environ, {"APPS_DOMAIN": "apps.test", "OIDC_ISSUER": self.actor.issuer,
                "OIDC_JWKS_URL": "http://unused", "DATABASE_KEY": "test" * 16})]
        for p in self.patches:
            p.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://platform.test")

    async def asyncTearDown(self):
        await self.client.aclose()
        main.app.dependency_overrides.clear()
        for p in reversed(self.patches):
            p.stop()
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    async def test_test_identity_listing_filters_runs_and_keeps_revoked_cleanup_handles(self):
        with self.connect() as conn:
            authorization.grant(conn, self.actor, "platform", None, "platform-admin")
            for name, kind, run_id, status in (
                ("reader", "test-persona", "run-1", "active"),
                ("retired-reader", "test-persona", "run-1", "revoked"),
                ("other-reader", "test-persona", "run-2", "active"),
                ("runner", "test-runner", None, "active"),
            ):
                conn.execute("""INSERT INTO deployment_credentials(
                    name, kind, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at, test_run_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()+interval '2 hours',%s)""",
                    (name, kind, "provider" if kind == "test-persona" else None,
                     self.actor.issuer, name, "client-" + name, "provider-" + name,
                     status, self.actor.issuer, self.actor.subject, run_id))
                if kind == "test-persona" and status == "active":
                    authorization.grant(conn, Principal(self.actor.issuer, name), "project", "provider", "viewer")
        for run_id, expected in (("run-1", {"reader", "retired-reader"}),
                                 ("run-2", {"other-reader"}), ("missing-run", set()),
                                 (None, {"reader", "retired-reader", "other-reader"})):
            with self.subTest(run_id=run_id):
                response = await self.client.get("/platform/test-identities",
                    params={"test_run_id": run_id} if run_id is not None else {})
                self.assertEqual(response.status_code, 200)
                records = response.json()["credentials"]
                self.assertEqual({r["name"] for r in records}, expected)
                for record in records:
                    self.assertEqual(record["kind"], "test-persona")
                    self.assertEqual(record["status"], "revoked" if record["name"] == "retired-reader" else "active")
                    self.assertEqual(record["role"], None if record["status"] == "revoked" else "viewer")
                    self.assertNotIn("client_secret", record)
                    self.assertNotIn("provider_client_id", record)
        self.active_actor = self.consumer
        denied = await self.client.get("/platform/test-identities", params={"test_run_id": "run-1"})
        self.assertEqual(denied.status_code, 403)

    async def group(self):
        response = await self.client.post("/v1/projects/provider/application-groups", json={"name": "readers", "displayName": "Readers"},
                                          headers={"Idempotency-Key": "readers-1"})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def policy(self):
        group = await self.group()
        body = {k: copy.deepcopy(POLICY["spec"][k]) for k in ("component", "defaultDecision", "identityAttributes", "routes")}
        for r in body["routes"]:
            r["authorization"]["anyOfGroups"] = ["readers"]
        response = await self.client.put("/v1/projects/provider/applications/provider/access-policy", json=body)
        self.assertEqual(response.status_code, 202, response.text)
        policy = response.json()
        with self.connect() as conn, store.locked(conn):
            policy = store.update(conn, store.get(conn, policy["id"]), state="active")
        return policy, group

    async def test_idempotent_groups_conflicting_keys_versions_and_role_separation(self):
        first = await self.group()
        second = await self.client.post("/v1/projects/provider/application-groups", json={"name": "readers", "displayName": "Readers"}, headers={"Idempotency-Key": "readers-1"})
        self.assertEqual(first["id"], second.json()["id"])
        changed = await self.client.post("/v1/projects/provider/application-groups", json={"name": "readers", "displayName": "Other"}, headers={"Idempotency-Key": "readers-1"})
        self.assertEqual(changed.status_code, 409)
        stale = await self.client.delete("/v1/projects/provider/application-groups/" + first["id"], headers={"If-Match": '"9"'})
        self.assertEqual(stale.status_code, 412)
        with self.connect() as conn:
            self.assertEqual(store.listing(conn, "membership"), [])
            self.assertEqual(conn.execute("SELECT count(*) FROM hosted_access_principals").fetchone()[0], 0)
        self.active_actor = self.consumer
        denied = await self.client.post("/v1/projects/provider/application-groups", json={"name": "wrong", "displayName": "Wrong"}, headers={"Idempotency-Key": "wrong-1"})
        self.assertEqual(denied.status_code, 403)

    async def test_first_login_approval_revocation_and_failed_provider_cleanup(self):
        policy, group = await self.policy()
        with self.connect() as conn, store.locked(conn):
            pid, request = store.enroll(conn, policy, self.actor.issuer, "human-1")
            pid2, same = store.enroll(conn, policy, self.actor.issuer, "human-1")
            self.assertEqual((pid, request["id"]), (pid2, same["id"]))
            self.assertEqual(store.listing(conn, "membership"), [])
        response = await self.client.post("/v1/projects/provider/application-access-requests/" + request["id"] + "/approve",
            json={"groups": [group["id"]]}, headers={"If-Match": '"1"'})
        self.assertEqual(response.status_code, 202, response.text)
        with self.connect() as conn:
            membership = store.listing(conn, "membership")[0]
            self.assertEqual(membership["state"], "provisioning")
        provider = Mock()
        # Discard the synthetic policy operation so the actual membership operation runs.
        with self.connect() as conn:
            conn.execute("UPDATE hosted_access_operations SET state='succeeded' WHERE action='policy.apply'")
        access_worker.process_one(main, lambda: provider)
        with self.connect() as conn:
            membership = store.get(conn, membership["id"])
            self.assertEqual(membership["state"], "active")
        response = await self.client.delete("/v1/projects/provider/application-group-memberships/" + membership["id"], headers={"If-Match": '"' + str(membership["version"]) + '"'})
        self.assertEqual(response.status_code, 202, response.text)
        provider.set_membership.side_effect = RuntimeError("sensitive provider failure must never be retained")
        access_worker.process_one(main, lambda: provider)
        with self.connect() as conn:
            self.assertEqual(store.get(conn, membership["id"])["state"], "revocation-pending")
            op = conn.execute("SELECT state, error_code FROM hosted_access_operations WHERE action='membership.revoke'").fetchone()
            self.assertEqual(op, ("running", "provider_unavailable"))

    async def test_pre_authorized_machine_approval_rotation_recovery_and_retirement(self):
        policy, group = await self.policy()
        self.active_actor = self.consumer
        response = await self.client.post("/v1/projects/consumer/service-access-requests",
            json={"name": "provider-reader", "providerProject": "provider", "application": "provider", "projectWideCredential": True},
            headers={"Idempotency-Key": "service-1"})
        self.assertEqual(response.status_code, 201, response.text)
        service = response.json()
        self.assertEqual(service["spec"]["credentials"], [])
        wrong = await self.client.post("/v1/projects/consumer/service-access-requests/" + service["id"] + "/approve", json={"groups": [group["id"]]}, headers={"If-Match": '"1"'})
        self.assertEqual(wrong.status_code, 404)
        self.active_actor = self.actor
        approved = await self.client.post("/v1/projects/provider/service-access-requests/" + service["id"] + "/approve", json={"groups": [group["id"]]}, headers={"If-Match": '"1"'})
        self.assertEqual(approved.status_code, 202, approved.text)
        with self.connect() as conn:
            conn.execute("UPDATE hosted_access_operations SET state='succeeded' WHERE action='policy.apply'")
        provider = Mock()
        provider.service.side_effect = lambda p, credential, groups: {"clientId": "service-" + credential, "subject": "subject-" + credential, "secret": "test-secret"}
        with patch.object(access_worker, "write_secret", return_value="1") as deliver, patch.object(access_worker, "confirm_secret"), patch.object(access_worker, "roll_services"):
            access_worker.process_one(main, lambda: provider)
            self.assertEqual(deliver.call_count, 3)
        with self.connect() as conn:
            service = store.get(conn, service["id"])
            self.assertEqual(service["state"], "active")
            self.assertNotIn("test-secret", json.dumps(service, default=str))
            pid = service["spec"]["principalId"]
        self.active_actor = self.consumer
        response = await self.client.post("/v1/projects/consumer/service-access-requests/" + service["id"] + "/rotate", json={"emergency": False},
                                          headers={"If-Match": '"' + str(service["version"]) + '"'})
        self.assertEqual(response.status_code, 202, response.text)
        with patch.object(access_worker, "write_secret", return_value="2"), patch.object(access_worker, "roll_services"):
            access_worker.process_one(main, lambda: provider)
        with self.connect() as conn:
            service = store.get(conn, service["id"])
            self.assertEqual(service["spec"]["principalId"], pid)
            self.assertEqual([c["state"] for c in service["spec"]["credentials"]], ["overlap", "active"])
            authorization.grant(conn, self.actor, "platform", None, "platform-admin")
        self.active_actor = self.actor
        recovered = await self.client.post("/operator/application-access/recover")
        self.assertEqual(recovered.status_code, 202, recovered.text)
        with self.connect() as conn, store.locked(conn):
            self.assertNotEqual(store.get(conn, policy["id"])["spec"]["sessionEpoch"], policy["spec"]["sessionEpoch"])
            service = store.get(conn, service["id"])
            self.assertEqual(service["state"], "provisioning")
            self.assertEqual([c["state"] for c in service["spec"]["credentials"]], ["revocation-pending", "revocation-pending", "provisioning"])
            store.retire(conn, "provider", self.actor)
            self.assertEqual(store.get(conn, service["id"])["state"], "revocation-pending")

    async def test_policy_activation_waits_for_all_ready_replicas_and_rollback(self):
        policy, group = await self.policy()
        body = {k: copy.deepcopy(policy["spec"][k]) for k in ("component", "defaultDecision", "identityAttributes", "routes")}
        body["routes"][1]["match"]["methods"] = ["GET"]
        update = await self.client.put("/v1/projects/provider/applications/provider/access-policy", json=body,
            headers={"If-Match": '"' + str(policy["version"]) + '"'})
        self.assertEqual(update.status_code, 202, update.text)
        provider = Mock()
        with patch.object(main, "apply"), patch.object(access_worker, "proxy_ready", return_value=True), \
             patch.object(access_worker, "ready_replicas", return_value={"replica-a", "replica-b"}):
            access_worker.process_one(main, lambda: provider)  # Superseded original operation.
            access_worker.process_one(main, lambda: provider)  # Stage, but do not activate.
            with self.connect() as conn:
                staged = store.get(conn, policy["id"])
                self.assertEqual(staged["state"], "activating")
                generation = staged["spec"]["stageGeneration"]
                conn.execute("INSERT INTO hosted_access_replicas(id,generation) VALUES ('replica-a',%s)", (generation,))
                conn.execute("UPDATE hosted_access_operations SET updated_at=now()-interval '3 seconds' WHERE state='running'")
            access_worker.process_one(main, lambda: provider)
            with self.connect() as conn:
                self.assertEqual(store.get(conn, policy["id"])["state"], "activating")
                conn.execute("INSERT INTO hosted_access_replicas(id,generation) VALUES ('replica-b',%s)", (generation,))
                conn.execute("UPDATE hosted_access_operations SET updated_at=now()-interval '3 seconds' WHERE state='running'")
            access_worker.process_one(main, lambda: provider)
        with self.connect() as conn:
            active = store.get(conn, policy["id"])
            self.assertEqual(active["state"], "active")
            self.assertEqual(len(store.listing(conn, "policy-revision")), 2)
        rollback = await self.client.post("/v1/projects/provider/applications/provider/access-policy/rollback",
            headers={"If-Match": '"' + str(active["version"]) + '"'})
        self.assertEqual(rollback.status_code, 202, rollback.text)
        self.assertEqual(rollback.json()["spec"]["routes"][1]["match"]["methods"], ["GET", "POST"])

    async def test_failed_grant_retry_rechecks_current_administrator_authority(self):
        policy, group = await self.policy()
        with self.connect() as conn, store.locked(conn):
            pid, request = store.enroll(conn, policy, self.actor.issuer, "retry-human")
        approved = await self.client.post("/v1/projects/provider/application-access-requests/" + request["id"] + "/approve",
            json={"groups": [group["id"]]}, headers={"If-Match": '"1"'})
        self.assertEqual(approved.status_code, 202, approved.text)
        with self.connect() as conn:
            conn.execute("UPDATE hosted_access_operations SET state='succeeded' WHERE action='policy.apply'")
            conn.execute("DELETE FROM platform_grants WHERE scope_kind='project' AND scope_id='provider'")
        provider = Mock()
        access_worker.process_one(main, lambda: provider)
        provider.set_membership.assert_not_called()
        with self.connect() as conn:
            membership = store.listing(conn, "membership")[0]
            self.assertEqual(membership["state"], "failed")
            operation = conn.execute("SELECT id::text FROM hosted_access_operations WHERE action='membership.grant'").fetchone()[0]
        denied = await self.client.post("/v1/access-operations/" + operation + "/retry",
            headers={"If-Match": '"' + str(membership["version"]) + '"'})
        self.assertEqual(denied.status_code, 403)
        with self.connect() as conn:
            authorization.grant(conn, self.actor, "project", "provider", "project-admin")
        retried = await self.client.post("/v1/access-operations/" + operation + "/retry",
            headers={"If-Match": '"' + str(membership["version"]) + '"'})
        self.assertEqual(retried.status_code, 202, retried.text)
        access_worker.process_one(main, lambda: provider)
        with self.connect() as conn:
            self.assertEqual(store.get(conn, membership["id"])["state"], "active")

    async def test_rotation_does_not_resurrect_pruned_revoked_machine_memberships(self):
        policy, group = await self.policy()
        pid = "prn_" + uuid4().hex
        with self.connect() as conn, store.locked(conn):
            service = store.create(conn, "service-access", "consumer", "revoked-group-service", {
                "providerProject": "provider", "policyId": policy["id"], "principalId": pid,
                "groups": [group["id"]], "membershipsEstablished": True,
                "credentials": [{"id": uuid4().hex, "state": "provisioning"}]}, "active")
            membership = store.create(conn, "membership", "provider", "old-membership", {
                "policyId": policy["id"], "principalId": pid, "groupId": group["id"]}, "revoked")
            conn.execute("UPDATE hosted_access_resources SET updated_at=now()-interval '91 days' WHERE id=%s", (membership["id"],))
            store.prune(conn)
            self.assertEqual(store.listing(conn, "membership"), [])
            provider = Mock()
            provider.service.return_value = {"clientId": "replacement", "subject": "replacement-subject", "secret": "synthetic"}
            with patch.object(access_worker, "write_secret", return_value="2"), patch.object(access_worker, "roll_services"), \
                 patch.object(access_worker, "confirm_secret"):
                access_worker.reconcile(conn, service, "service.rotate", self.consumer, provider, Mock(), Mock(), Mock())
            self.assertEqual(provider.service.call_args.args[2], [])
            self.assertEqual(store.listing(conn, "membership"), [])

    async def test_snapshot_quarantine_recovery_and_changed_backend_fail_closed(self):
        policy, group = await self.policy()
        headers = {"Authorization": "Bearer " + derived_secret("platform", "internal")}
        unauthorized = await self.client.get("/internal/application-access/snapshot")
        self.assertEqual(unauthorized.status_code, 401)
        current = await self.client.get("/internal/application-access/snapshot", headers=headers)
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(len(current.json()["policies"]), 1)
        with self.connect() as conn:
            conn.execute("INSERT INTO hosted_access_metadata(key,value) VALUES ('recovery-required','true')")
            store.bump(conn)
            authorization.grant(conn, self.actor, "platform", None, "platform-admin")
        quarantined = await self.client.get("/internal/application-access/snapshot", headers=headers)
        self.assertTrue(quarantined.json()["recoveryRequired"])
        self.assertEqual(quarantined.json()["policies"], [])
        recovered = await self.client.post("/operator/application-access/recover")
        self.assertEqual(recovered.status_code, 202, recovered.text)
        staged = await self.client.get("/internal/application-access/snapshot", headers=headers)
        self.assertFalse(staged.json()["recoveryRequired"])
        self.assertEqual(staged.json()["policies"][0]["state"], "provisioning")
        self.assertNotEqual(staged.json()["policies"][0]["spec"]["sessionEpoch"], policy["spec"]["sessionEpoch"])
        with self.connect() as conn:
            conn.execute("UPDATE projects SET spec=jsonb_set(spec,'{components,0,ports,0,port}','9090') WHERE name='provider'")
        changed = await self.client.get("/internal/application-access/snapshot", headers=headers)
        self.assertEqual(changed.json()["policies"], [])

    async def test_request_expiry_rejected_reopening_and_governance_email(self):
        policy, group = await self.policy()
        with self.connect() as conn, store.locked(conn):
            pid, request = store.enroll(conn, policy, self.actor.issuer, "human-expired")
            store.update(conn, request, spec={**request["spec"], "expiresAt": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
            store.prune(conn)
            request = store.get(conn, request["id"])
            self.assertEqual(request["state"], "expired")
            pid, request = store.enroll(conn, policy, self.actor.issuer, "human-expired")
            self.assertEqual(request["state"], "pending")
        rejected = await self.client.post("/v1/projects/provider/application-access-requests/" + request["id"] + "/reject", headers={"If-Match": '"' + str(request["version"]) + '"'})
        self.assertEqual(rejected.status_code, 200, rejected.text)
        with self.connect() as conn, store.locked(conn):
            _, request = store.enroll(conn, policy, self.actor.issuer, "human-expired")
            self.assertEqual(request["state"], "rejected")
        body = {k: copy.deepcopy(POLICY["spec"][k]) for k in ("component", "defaultDecision", "identityAttributes", "routes")}
        for r in body["routes"]:
            r["authorization"]["anyOfGroups"] = [group["id"]]
        body["identityAttributes"]["email"] = True
        response = await self.client.put("/v1/projects/provider/applications/provider/access-policy", json=body, headers={"If-Match": '"' + str(policy["version"]) + '"'})
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
