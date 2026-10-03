import os
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.identity import Principal
from app.operations import process_one


class OperationConnection:
    def __init__(self, state="queued", current_revision=1):
        self.operation_id = "operation-1"
        self.application_id = "application-1"
        self.project_id = "project-1"
        self.project_name = "smoke"
        self.actor_issuer = "https://issuer.example"
        self.actor_subject = "subject-1"
        self.revision = 1
        self.operation_kind = "deploy"
        self.state = state
        self.current_revision = current_revision
        self.spec = {"name": "smoke", "image": "example:v1", "port": 8080, "probe_profile": "status"}
        self.envelope = {
            "project_id": self.project_id,
            "application_id": self.application_id,
            "project_slug": self.project_name,
            "revision": self.revision,
            "spec": self.spec,
        }
        self.project_status = "provisioning"
        self.result = []
        self.events = []
        self.attempt_count = 0
        self.operation_result = None
        self.error_code = None
        self.last_restart = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=()):
        self.events.append(query)
        if query.startswith("SELECT operation_id FROM application_operations"):
            self.result = [(self.operation_id,)] if self.state in {"queued", "running"} else []
        elif query.startswith("SELECT pg_try_advisory_lock"):
            self.result = [(True,)]
        elif query.startswith("SELECT o.operation_id"):
            self.result = [(
                self.operation_id, self.application_id, self.revision, self.operation_kind,
                self.state, 1, self.envelope, self.actor_issuer, self.actor_subject,
                self.project_id, self.project_name, self.project_status,
            )]
        elif query.startswith("UPDATE application_operations SET state='running'"):
            self.state = "running"
            self.attempt_count += 1
        elif query.startswith("SELECT latest_restart.operation_id"):
            self.result = [(self.last_restart,)] if self.last_restart else []
        elif query.startswith("SELECT revision, spec FROM application_revisions"):
            self.result = [(self.current_revision, self.spec)]
        elif query.startswith("UPDATE projects SET status='failed'"):
            self.project_status = "failed"
        elif query.startswith("UPDATE projects SET status='applied'"):
            self.project_status = "applied"
        elif query.startswith("UPDATE application_operations SET state='failed'"):
            self.state = "failed"
            self.operation_result = params[0].obj
            self.error_code = params[1]
        elif query.startswith("UPDATE application_operations SET state='succeeded'"):
            self.state = "succeeded"
            self.operation_result = params[0].obj
            self.error_code = None
        return self

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0] if self.result else None


class OperationWorkerFixture(unittest.TestCase):
    def setUp(self):
        self.conn = OperationConnection()
        self.connect = Mock(return_value=self.conn)
        self.provision_database = Mock()
        self.apply = Mock()
        self.resources = Mock(return_value=[self.secret(), self.deployment()])
        self.publish_catalog = Mock()
        self.log = Mock()
        self.environment = patch.dict(os.environ, {
            "APPS_DOMAIN": "apps.localhost",
            "POSTGRES_IP": "172.30.80.10",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.authorization = patch("app.operations.is_allowed", return_value=True)
        self.authorization.start()
        self.addCleanup(self.authorization.stop)
        self.audit_patch = patch("app.operations.record_event", return_value=17)
        self.audit_mock = self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)

    @staticmethod
    def secret():
        return {"kind": "Secret", "metadata": {"name": "database"}}

    @staticmethod
    def deployment():
        return {"kind": "Deployment", "metadata": {"name": "smoke"},
                "spec": {"template": {"metadata": {"labels": {"app": "smoke"}}}}}

    @staticmethod
    def marker(manifest):
        return manifest["spec"]["template"]["metadata"].get("annotations", {}).get(
            "platform.example/restarted-by")

    def run_one(self):
        return process_one(
            self.connect, lambda name: "derived-password", self.provision_database,
            self.apply, self.resources, self.publish_catalog, self.log,
        )


class OperationWorkerTests(OperationWorkerFixture):
    def test_deploys_the_resolved_digest_reference_and_falls_back_for_legacy_specs(self):
        digest_image = "example@sha256:" + "a" * 64
        for resolved, expected in ((digest_image, digest_image), (None, "example:v1")):
            with self.subTest(resolved=resolved):
                self.conn = OperationConnection()
                self.connect.return_value = self.conn
                self.resources.reset_mock()
                if resolved:
                    self.conn.spec = {**self.conn.spec, "resolved_image": resolved}
                    self.conn.envelope = {**self.conn.envelope, "spec": self.conn.spec}
                self.assertTrue(self.run_one())
                self.assertEqual(self.resources.call_args.args[1], expected)

    def test_deploys_requested_resources_and_defaults_for_legacy_specs(self):
        wanted = {"requests": {"cpu": "250m", "memory": "128Mi"}, "limits": {"cpu": "1000m", "memory": "512Mi"}}
        for resources, expected in ((wanted, wanted), (None, None)):
            with self.subTest(resources=resources):
                self.conn = OperationConnection()
                self.connect.return_value = self.conn
                self.resources.reset_mock()
                if resources:
                    self.conn.spec = {**self.conn.spec, "resources": resources}
                    self.conn.envelope = {**self.conn.envelope, "spec": self.conn.spec}
                self.assertTrue(self.run_one())
                self.assertEqual(self.resources.call_args.args[6:], (expected,))

    def test_reclaims_running_operation_after_worker_restart_and_completes_it(self):
        self.conn.state = "running"

        self.assertTrue(self.run_one())

        self.assertEqual(self.conn.state, "succeeded")
        self.assertEqual(self.conn.attempt_count, 1)
        self.assertEqual(self.conn.project_status, "applied")
        self.assertEqual(self.conn.operation_result["status"], "applied")
        self.provision_database.assert_called_once_with(
            self.conn, "smoke", "derived-password")
        self.resources.assert_called_once()
        self.assertEqual([call.args[0] for call in self.apply.call_args_list],
                         [self.secret(), self.deployment()])
        self.publish_catalog.assert_called_once_with(self.conn)
        self.assertEqual(self.audit_mock.call_args.kwargs["operation_id"], self.conn.operation_id)

    def test_current_grant_is_rechecked_before_provider_side_effects(self):
        with patch("app.operations.is_allowed", return_value=False):
            self.assertTrue(self.run_one())

        self.assertEqual(self.conn.state, "failed")
        self.assertEqual(self.conn.error_code, "authorization_revoked")
        self.assertEqual(self.conn.project_status, "failed")
        self.provision_database.assert_not_called()
        self.apply.assert_not_called()
        self.assertEqual(self.audit_mock.call_args.args[4], "denied")
        self.assertEqual(self.audit_mock.call_args.args[0].identifier, Principal(
            self.conn.actor_issuer, self.conn.actor_subject).audit_id)

    def test_stale_revision_is_rejected_without_applying_old_spec(self):
        self.conn.current_revision = 2

        self.assertTrue(self.run_one())

        self.assertEqual(self.conn.state, "failed")
        self.assertEqual(self.conn.error_code, "stale_revision")
        self.provision_database.assert_not_called()
        self.apply.assert_not_called()

    def test_provider_failure_is_recorded_without_exposing_exception_text(self):
        self.apply.side_effect = RuntimeError("sensitive provider detail")

        self.assertTrue(self.run_one())

        self.assertEqual(self.conn.state, "failed")
        self.assertEqual(self.conn.error_code, "provider_error")
        self.assertEqual(self.conn.project_status, "failed")
        self.assertNotIn("sensitive provider detail", str(self.conn.operation_result))
        self.assertEqual(self.audit_mock.call_args.args[4], "failed")
        self.log.error.assert_called()


class RestartOperationTests(OperationWorkerFixture):
    def setUp(self):
        super().setUp()
        self.conn.operation_kind = "restart"
        self.conn.project_status = "applied"

    def test_interrupted_restart_reapplies_only_the_deployment_with_its_operation_marker(self):
        self.conn.state = "running"

        self.assertTrue(self.run_one())

        self.assertEqual(self.conn.state, "succeeded")
        self.assertEqual(self.conn.attempt_count, 1)
        self.assertEqual(self.conn.operation_result["status"], "restarted")
        self.assertEqual(self.conn.project_status, "applied")
        self.apply.assert_called_once()
        self.assertEqual(self.marker(self.apply.call_args.args[0]), self.conn.operation_id)
        self.provision_database.assert_not_called()
        self.publish_catalog.assert_not_called()

    def test_restart_of_a_project_that_is_not_applied_is_rejected_without_provider_calls(self):
        self.conn.project_status = "failed"

        self.assertTrue(self.run_one())

        self.assertEqual(self.conn.state, "failed")
        self.assertEqual(self.conn.error_code, "not_deployed")
        self.assertEqual(self.conn.project_status, "failed")
        self.apply.assert_not_called()

    def test_later_deployment_keeps_the_latest_restart_marker_to_avoid_a_second_rollout(self):
        self.conn.operation_kind = "deploy"
        self.conn.last_restart = "restart-operation-0"

        self.assertTrue(self.run_one())

        secret, deployment = [call.args[0] for call in self.apply.call_args_list]
        self.assertEqual(secret, self.secret())
        self.assertEqual(self.marker(deployment), "restart-operation-0")
        self.assertEqual(self.marker(self.deployment()), None)


if __name__ == "__main__":
    unittest.main()
