"""Offline contract and cleanup-scope checks for the preservation drill."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app/src"))
from acceptance import data_preservation as drill

RUN_ID = "0123456789ab"
IMAGE = "docker.io/example/web-postgres@sha256:" + "a" * 64
BINDING = "11111111-1111-1111-1111-111111111111"


class DataPreservationTests(TestCase):
    def test_plan_is_offline_and_scoped(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = drill.main(["plan", "--run-id", RUN_ID, "--fixture-image", IMAGE])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["project"], "dp-" + RUN_ID)
            self.assertFalse((Path(temporary) / ".runtime").exists())

    def test_run_requires_exact_origin_confirmation(self):
        args = drill.parser().parse_args(["run", "--run-id", RUN_ID, "--fixture-image", IMAGE])
        with self.assertRaisesRegex(drill.DrillError, "explicit_environment_confirmation_required"):
            drill.validate(args)

    def test_declaration_is_valid_named_binding_and_has_real_revision_difference(self):
        from app.spec import ApplicationEnvelopeV1Alpha2, to_flat
        one = drill.declaration("dp-" + RUN_ID, IMAGE, RUN_ID, BINDING, "500m")
        two = drill.declaration("dp-" + RUN_ID, IMAGE, RUN_ID, BINDING, "600m")
        for spec in (one, two):
            ApplicationEnvelopeV1Alpha2.model_validate(spec)
            flat = to_flat(spec)
            self.assertEqual(flat["components"][0]["bindings"][0]["bindingId"], BINDING)
            self.assertEqual(flat["configuration"]["ACCEPTANCE_RUN_ID"], RUN_ID)
            self.assertNotIn("exposure", flat["components"][0])
        self.assertNotEqual(to_flat(one)["components"][0]["resources"],
                            to_flat(two)["components"][0]["resources"])

    def test_uncertain_project_create_never_retires_unproven_project(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            report.data["projectCreateAttempted"] = True
            report.save()
            class API:
                def request(self, *args, **kwargs):
                    raise AssertionError("cleanup must not query or mutate an unproven project")
            drill.retire(API(), report)
            self.assertEqual(report.data["cleanup"], "incomplete-retry-required")
            path = report.directory / "report.json"
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(report.directory.stat().st_mode & 0o777, 0o700)

    def test_visit_uses_only_owned_namespace_and_reports_safe_failure(self):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "a private credential must not appear in an error"
        with patch.object(drill.subprocess, "run", return_value=Result()) as process:
            with self.assertRaisesRegex(drill.DrillError, "fixture_visit_failed"):
                drill.visit(Path("/tmp/kubectl"), Path("/tmp/kubeconfig"), "dp-" + RUN_ID)
        command = process.call_args.args[0]
        self.assertEqual(command[command.index("-n") + 1], "project-dp-" + RUN_ID)
