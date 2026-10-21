import json
import sys
import unittest
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.deployment_credentials import CredentialAccess
from app.identity import Principal

from app import main


class Result:
    def __init__(self, rows=(), rowcount=0):
        self.rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class AutomationConnection:
    runner_id = UUID("00000000-0000-0000-0000-000000000201")
    persona_id = UUID("00000000-0000-0000-0000-000000000202")

    def __init__(self, duplicate_project=False):
        self.now = datetime(2026, 10, 4, tzinfo=UTC)
        self.duplicate_project = duplicate_project
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=()):
        self.statements.append((query, params))
        if query.startswith("INSERT INTO projects"):
            return Result(
                [] if self.duplicate_project else [(params[0], "empty", self.now)]
            )
        if query.startswith("SELECT 1 FROM projects"):
            return Result([(1,)])
        if "INSERT INTO deployment_credentials" in query and "'test-runner'" in query:
            return Result(
                [
                    (
                        self.runner_id,
                        "suite",
                        "test-runner",
                        None,
                        "default",
                        "active",
                        self.now,
                        self.now + timedelta(days=7),
                        False,
                        None,
                        None,
                        None,
                    )
                ]
            )
        if "INSERT INTO deployment_credentials" in query and "'test-persona'" in query:
            return Result(
                [
                    (
                        self.persona_id,
                        "viewer",
                        "test-persona",
                        "test-project",
                        "default",
                        "active",
                        self.now,
                        self.now + timedelta(hours=2),
                        False,
                        None,
                        None,
                        "run-1",
                    )
                ]
            )
        return Result()


class PlatformAutomationApiTests(unittest.TestCase):
    human = Principal("https://issuer.example", "human-admin", "Human Admin")

    def test_empty_project_creation_has_no_initial_specification(self):
        conn = AutomationConnection()
        with (
            patch.object(main, "require_platform_admin"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=conn),
        ):
            response = main.create_empty_project(
                main.EmptyProjectCreate(name="test-project"), self.human
            )
        body = json.loads(response.body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            body,
            {
                "name": "test-project",
                "status": "empty",
                "spec": None,
                "created_at": "2026-10-04T00:00:00+00:00",
            },
        )
        insert = next(
            (query, params)
            for query, params in conn.statements
            if query.startswith("INSERT INTO projects")
        )
        self.assertIn("NULL, 'empty'", insert[0])

    def test_duplicate_empty_project_is_a_conflict(self):
        conn = AutomationConnection(duplicate_project=True)
        with (
            patch.object(main, "require_platform_admin"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=conn),
        ):
            response = main.create_empty_project(
                main.EmptyProjectCreate(name="test-project"), self.human
            )
        self.assertEqual(response.status_code, 409)

    def test_human_admin_creates_test_runner_and_receives_secret_once(self):
        conn = AutomationConnection()
        provider = {
            "provider_resource_id": "runner-provider",
            "client_id": "platform-ci-runner",
            "client_secret": "runner-secret",
            "subject": "runner-subject",
        }
        with (
            patch.object(main, "require_human_platform_admin"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=conn),
            patch.object(main, "verifier", Mock(issuer="https://issuer.example")),
            patch.object(main, "create_credential_client", return_value=provider),
        ):
            response = main.create_test_runner_credential(
                main.TestRunnerCredentialCreate(name="suite"), self.human
            )
        body = json.loads(response.body)
        self.assertEqual(body["kind"], "test-runner")
        self.assertEqual(body["client_secret"], "runner-secret")
        self.assertEqual(
            body["token_endpoint"],
            "https://issuer.example/protocol/openid-connect/token",
        )
        grant = next(
            params
            for query, params in conn.statements
            if "INSERT INTO platform_grants" in query
        )
        self.assertEqual(grant[-1], "platform-admin")

    def test_test_runner_creates_scoped_viewer_persona(self):
        conn = AutomationConnection()
        provider = {
            "provider_resource_id": "viewer-provider",
            "client_id": "platform-ci-viewer",
            "client_secret": "viewer-secret",
            "subject": "viewer-subject",
        }
        runner = Principal("https://issuer.example", "runner-subject", "Runner")
        body = main.TestIdentityCreate(
            name="viewer", role="viewer", project="test-project", test_run_id="run-1"
        )
        with (
            patch.object(main, "require_test_identity_manager"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=conn),
            patch.object(main, "verifier", Mock(issuer="https://issuer.example")),
            patch.object(main, "create_credential_client", return_value=provider),
        ):
            response = main.create_test_identity(body, runner)
        created = json.loads(response.body)
        self.assertEqual(created["kind"], "test-persona")
        self.assertEqual(created["role"], "viewer")
        grant = next(
            params
            for query, params in conn.statements
            if "INSERT INTO platform_grants" in query
        )
        self.assertEqual(grant[-2:], ("test-project", "viewer"))

    def test_machine_platform_admin_cannot_create_a_root_test_runner(self):
        machine = Principal("https://issuer.example", "machine-admin", "Machine Admin")
        access = CredentialAccess(UUID(int=9), "test-runner", None, True)
        with (
            patch.object(main, "require_platform_admin"),
            patch.object(main, "connect") as connect,
        ):
            connect.return_value.__enter__.return_value = Mock()
            with (
                patch.object(main, "access_scope", return_value=access),
                patch.object(main, "required_audit"),
                self.assertRaises(HTTPException) as raised,
            ):
                main.require_human_platform_admin(machine)
        self.assertEqual(raised.exception.status_code, 403)

    def test_preflight_accepts_only_humans_and_active_root_test_runners(self):
        cases = [
            (None, "human"),
            (CredentialAccess(UUID(int=1), "test-runner", None, True), "test-runner"),
            (CredentialAccess(UUID(int=1), "test-runner", None, False), None),
            (CredentialAccess(UUID(int=2), "test-persona", None, True), None),
            (CredentialAccess(UUID(int=3), "deployment", "demo", True), None),
        ]
        for access, expected in cases:
            with (
                self.subTest(access=access),
                patch.object(main, "connect", return_value=AutomationConnection()),
                patch.object(main, "require_platform_admin"),
                patch.object(main, "access_scope", return_value=access),
                patch.object(main, "required_audit"),
            ):
                if expected is None:
                    with self.assertRaises(HTTPException) as denied:
                        main.test_context(self.human)
                    self.assertEqual(denied.exception.status_code, 403)
                else:
                    self.assertEqual(main.test_context(self.human), {"kind": expected})

    def test_runner_cannot_administer_credentials_or_change_human_policy(self):
        access = CredentialAccess(UUID(int=1), "test-runner", None, True)
        calls = [
            lambda: main.create_test_runner_credential(
                main.TestRunnerCredentialCreate(name="forbidden"), self.human
            ),
            lambda: main.list_test_runner_credentials(self.human),
            lambda: main.rotate_test_runner_credential(
                UUID(int=1), main.DeploymentCredentialRotate(), self.human
            ),
            lambda: main.revoke_test_runner_credential(UUID(int=1), self.human),
            lambda: main.set_ai_policy(
                "demo", main.AIProjectPolicy(classification="internal"), self.human
            ),
        ]
        with (
            patch.object(main, "connect", return_value=AutomationConnection()),
            patch.object(main, "require_platform_admin"),
            patch.object(main, "access_scope", return_value=access),
            patch.object(main, "required_audit"),
        ):
            for call in calls:
                with self.assertRaises(HTTPException) as denied:
                    call()
                self.assertEqual(denied.exception.status_code, 403)

    def test_host_issuance_records_system_actor_and_keeps_existing_ttl(self):
        from app.audit import Actor
        from app.automation_credentials import issue_test_runner

        provider = {
            "provider_resource_id": "provider",
            "client_id": "client",
            "client_secret": "secret",
            "subject": "runner",
        }
        conn = AutomationConnection()
        actor = Actor("system", "host-test-runner-bootstrap")
        principal = Principal("https://issuer.example", "host-test-runner-bootstrap")
        with (
            patch.object(main, "connect", return_value=conn),
            patch.object(main, "verifier", Mock(issuer=principal.issuer)),
            patch.object(main, "create_credential_client", return_value=provider),
            patch.object(main, "required_audit") as audit,
        ):
            result = issue_test_runner(
                main,
                main.TestRunnerCredentialCreate(name="suite", expires_in_days=1),
                principal,
                actor,
            )
        self.assertEqual(result["client_secret"], "secret")
        self.assertEqual(audit.call_args.args[0], actor)
        self.assertEqual(audit.call_args.args[1], "test-runner-credential.create")
        insert = next(
            params
            for query, params in conn.statements
            if "INSERT INTO deployment_credentials" in query
        )
        self.assertEqual(insert[-1], 1)

    def test_test_identity_listing_types_optional_run_filter(self):
        for run_id in (None, "run-1"):
            with self.subTest(run_id=run_id):
                conn = AutomationConnection()
                with (
                    patch.object(main, "require_test_identity_manager") as authorize,
                    patch.object(main, "required_audit") as audit,
                    patch.object(main, "connect", return_value=conn),
                ):
                    response = main.list_test_identities(run_id, self.human)
                self.assertEqual(response, {"credentials": []})
                authorize.assert_called_once_with(self.human)
                query, params = conn.statements[0]
                self.assertIn("(%s::text IS NULL OR test_run_id=%s)", query)
                self.assertEqual(params, (run_id, run_id))
                self.assertIn("kind='test-persona'", query)
                audit.assert_called_once_with(
                    main.actor_for(self.human),
                    "test-identity.list",
                    "test-run",
                    run_id,
                    "succeeded",
                    {"scope": "platform"},
                    {"count": 0},
                )


if __name__ == "__main__":
    unittest.main()
