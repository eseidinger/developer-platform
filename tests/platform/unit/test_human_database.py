"""Offline safety and contract checks for the opt-in database drill."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.platform import human_database as drill


IMAGE = "docker.io/example/neutral-fixture@sha256:" + "a" * 64
RUN_ID = "0123456789ab"


class HumanDatabaseDrillTests(unittest.TestCase):
    def test_plan_is_offline_and_does_not_create_report(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = drill.main(["plan", "--run-id", RUN_ID, "--fixture-image", IMAGE])
            plan = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertFalse(plan["mutates"])
            self.assertEqual(plan["projects"], ["hd-0123456789ab-a", "hd-0123456789ab-b"])
            self.assertFalse((Path(temporary) / ".runtime").exists())

    def test_live_requires_explicit_origin_and_private_file_paths(self):
        args = drill.parser().parse_args(["run", "--run-id", RUN_ID, "--fixture-image", IMAGE])
        with self.assertRaisesRegex(drill.DrillError, "explicit_environment_confirmation_required"):
            drill.validate(args)
        args.confirm_environment = "http://127.0.0.1:8000"
        with self.assertRaisesRegex(drill.DrillError, "protected_session_and_host_key_required"):
            drill.validate(args)

    def test_declaration_is_a_valid_private_postgres_fixture(self):
        from app.spec import ApplicationEnvelopeV1Alpha2

        project = "hd-0123456789ab-a"
        declaration = drill.declaration(project, IMAGE, RUN_ID)
        ApplicationEnvelopeV1Alpha2.model_validate(declaration)
        component = declaration["spec"]["components"][0]
        self.assertEqual(component["exposure"], "private")
        self.assertEqual(component["health"]["readiness"]["path"], "/health/ready")
        self.assertNotIn("resources", declaration["spec"])
        self.assertEqual(component["bindings"], [])
        bound = drill.declaration(project, IMAGE, RUN_ID, "11111111-1111-1111-1111-111111111111")
        ApplicationEnvelopeV1Alpha2.model_validate(bound)
        self.assertEqual(len(bound["spec"]["components"][0]["bindings"]), 1)

    def test_ssh_requires_pinned_host_key_and_only_one_forward(self):
        command = drill.ssh_command(Path("/tmp/key"), Path("/tmp/known_hosts"),
                                    "127.0.0.1", 2222, 15432, "172.30.80.10:5432")
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("UserKnownHostsFile=/tmp/known_hosts", command)
        self.assertIn("127.0.0.1:15432:172.30.80.10:5432", command)
        self.assertEqual(command.count("-L"), 1)

    def test_private_report_contains_only_safe_fields_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            report.check("ungranted-key-denied", True)
            path = report.directory / "report.json"
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(report.directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(path.read_text())["checks"][0]["name"], "ungranted-key-denied")
            with self.assertRaisesRegex(drill.DrillError, "run_directory_exists"):
                drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)

    def test_cleanup_finds_persona_when_create_response_was_lost(self):
        class FakeAPI:
            def __init__(self):
                self.deleted = []

            def request(self, method, path, *args, **kwargs):
                if method == "GET":
                    return {"credentials": [{"credential_id": "persona-id", "test_run_id": RUN_ID,
                        "name": "human-db-denial-" + RUN_ID, "project": "hd-" + RUN_ID + "-a",
                        "status": "active"}]}
                self.deleted.append(path)
                return {"status": "revoked"}

        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            api = FakeAPI()
            subject = drill.Drill(SimpleNamespace(run_id=RUN_ID), {}, api, report)
            subject.persona_creation_attempted = True
            self.assertTrue(subject.cleanup())
            self.assertEqual(api.deleted, ["/platform/test-identities/persona-id"])


if __name__ == "__main__":
    unittest.main()
