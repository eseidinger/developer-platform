"""Trusted-host credential output must be private and never overwritten."""

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_test_runner", ROOT / "scripts/setup/bootstrap-test-runner.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTestRunnerTests(unittest.TestCase):
    def args(self, directory):
        return Namespace(
            api="http://127.0.0.1:8000",
            confirm_environment="http://127.0.0.1:8000",
            output=Path(directory) / "runner.json",
            name="suite",
            expires_in_days=1,
        )

    def result(self):
        return Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "token_endpoint": "https://identity.example/token",
                    "client_id": "runner",
                    "client_secret": "private-value",
                    "credential_id": "id",
                    "expires_at": "2030-01-01T00:00:00Z",
                }
            ),
        )

    def test_private_output_compatible_with_ansible_without_secret_arguments(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                bootstrap.subprocess, "run", return_value=self.result()
            ) as run,
        ):
            args = self.args(directory)
            self.assertEqual(bootstrap.bootstrap(args), "id")
            self.assertEqual(args.output.stat().st_mode & 0o777, 0o600)
            payload = json.loads(args.output.read_text())
            self.assertEqual(
                payload["platform_test_runner_client_secret"], "private-value"
            )
            self.assertNotIn("private-value", str(run.call_args))
            self.assertEqual(
                json.loads(run.call_args.kwargs["input"])["expires_in_days"], 1
            )

    def test_existing_credential_is_never_overwritten_or_reissued(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            args = self.args(directory)
            args.output.write_text("existing")
            with self.assertRaises(FileExistsError):
                bootstrap.bootstrap(args)
            self.assertEqual(args.output.read_text(), "existing")
            run.assert_not_called()

    def test_symlink_output_is_rejected_before_issuance(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            args = self.args(directory)
            target = Path(directory) / "original"
            target.write_text("existing")
            args.output.symlink_to(target)
            with self.assertRaises(FileExistsError):
                bootstrap.bootstrap(args)
            self.assertEqual(target.read_text(), "existing")
            run.assert_not_called()

    def test_failed_issuance_removes_only_reserved_output(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                bootstrap.subprocess,
                "run",
                return_value=Mock(returncode=1, stderr="private-value"),
            ),
        ):
            args = self.args(directory)
            with self.assertRaisesRegex(
                RuntimeError, "^Host bootstrap failed; inspect private API diagnostics$"
            ):
                bootstrap.bootstrap(args)
            self.assertFalse(args.output.exists())

    def test_confirmation_is_checked_before_creating_a_credential(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            args = self.args(directory)
            args.confirm_environment = "https://other.example"
            with self.assertRaisesRegex(ValueError, "Confirm a valid"):
                bootstrap.bootstrap(args)
            run.assert_not_called()
