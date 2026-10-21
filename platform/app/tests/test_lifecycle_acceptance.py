"""Offline safety contracts for scoped lifecycle execution and cleanup."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from acceptance.harness import DrillError
from acceptance.lifecycle import logs, runner

RUN = "0123456789ab"
IMAGE = "ghcr.io/example/fixture@sha256:" + "a" * 64


class LifecycleTests(unittest.TestCase):
    def arguments(self, *extra):
        return ["plan", "--run-id", RUN, "--fixture-image", IMAGE, *extra]

    def fixture(self, api):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = patch.object(runner, "ROOT", Path(temporary.name))
        root.start()
        self.addCleanup(root.stop)
        return runner.Fixture(runner.parser().parse_args(self.arguments()), api)

    def test_plan_never_reads_credentials_or_contacts_services(self):
        with (
            patch.object(
                runner, "settings", side_effect=AssertionError("read settings")
            ),
            patch.object(runner, "API", side_effect=AssertionError("network")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(runner.main(self.arguments()), 0)
        plan = json.loads(output.getvalue())
        self.assertFalse(plan["mutates"])
        self.assertEqual(plan["project"], "lc-" + RUN)
        self.assertIn("audit", plan["checks"])

    def test_live_requires_environment_confirmation_and_ungranted_identity(self):
        args = runner.parser().parse_args(self.arguments())
        args.command = "run"
        with self.assertRaisesRegex(DrillError, "environment_confirmation"):
            runner.validate(args, False)
        args.confirm_environment = args.api
        args.operator_token_file = Path("session.json")
        with self.assertRaisesRegex(DrillError, "ungranted_user"):
            runner.validate(args, False)
        runner.validate(args, True)

    def test_invalid_scope_or_mutable_image_is_rejected(self):
        for option, value in (
            ("--run-id", "../../existing"),
            ("--fixture-image", "fixture:latest"),
            ("--fixture-port", "80"),
        ):
            args = runner.parser().parse_args(self.arguments(option, value))
            with self.assertRaises(DrillError):
                runner.validate(args, False)

    def test_existing_project_is_never_adopted_or_retired(self):
        api = Mock()
        api.request.side_effect = [{}, [{"name": "lc-" + RUN}]]
        fixture = self.fixture(api)
        with self.assertRaisesRegex(DrillError, "fixture_project_exists"):
            fixture.provision()
        fixture.retire()
        self.assertFalse(fixture.created)
        self.assertTrue(
            all(call.args[0] == "GET" for call in api.request.call_args_list)
        )

    def test_lost_create_response_requires_manual_review_without_deleting_project(self):
        api = Mock()
        api.request.side_effect = [{}, [], OSError("lost response")]
        fixture = self.fixture(api)
        with self.assertRaises(OSError):
            fixture.provision()
        fixture.retire()
        self.assertFalse(fixture.created)
        self.assertTrue(fixture.report["cleanup"].startswith("incomplete"))
        self.assertEqual(len(api.request.call_args_list), 3)

    def test_retirement_is_idempotent_and_keeps_data(self):
        api = Mock()
        api.request.return_value = {
            "status": "retired",
            "blockers": ["already_retired"],
        }
        fixture = self.fixture(api)
        fixture.created = True
        fixture.retire()
        self.assertEqual(fixture.report["cleanup"], "retired-data-retained")
        api.request.assert_called_once_with(
            "GET", "/projects/lc-" + RUN + "/retirement-preview", None
        )

    def test_run_attempts_cleanup_after_provision_failure(self):
        args = self.arguments()
        args[0] = "run"
        args += [
            "--confirm-environment",
            "http://127.0.0.1:8000",
            "--operator-token-file",
            "session.json",
        ]
        fixture = Mock()
        fixture.report = {"cleanup": "pending"}
        fixture.provision.side_effect = DrillError("fixture_readiness_timeout")
        fixture.retire.side_effect = lambda: fixture.report.update(
            cleanup="retired-data-retained"
        )
        fixture.output = Path("report")
        with (
            patch.object(runner, "settings", return_value={}),
            patch.object(runner, "Keycloak"),
            patch.object(runner, "operator_tokens"),
            patch.object(runner, "API"),
            patch.object(runner, "Fixture", return_value=fixture),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(runner.main(args, smoke=True), 1)
        fixture.retire.assert_called_once()
        self.assertEqual(fixture.report["errorCode"], "fixture_readiness_timeout")
        self.assertEqual(fixture.report["result"], "failed")

    def test_failed_log_pod_creation_still_attempts_scoped_cleanup(self):
        fixture = Mock()
        fixture.project = "lc-" + RUN
        fixture.args.fixture_image = IMAGE
        fixture.kubectl.side_effect = [OSError("lost apply response"), Mock()]
        with self.assertRaises(OSError):
            logs.check_logs(fixture)
        apply, delete = fixture.kubectl.call_args_list
        pod = json.loads(apply.kwargs["input"])
        self.assertEqual(pod["spec"]["containers"][0]["image"], IMAGE)
        self.assertEqual(pod["metadata"]["namespace"], "project-lc-" + RUN)
        self.assertEqual(delete.args[:2], ("delete", "pod"))
        self.assertEqual(delete.args[2], pod["metadata"]["name"])


if __name__ == "__main__":
    unittest.main()
