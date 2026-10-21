"""Offline scope and public declaration checks for the isolation drill."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tests.platform import isolation as drill

RUN_ID = "0123456789ab"
IMAGE = "docker.io/example/web-postgres@sha256:" + "a" * 64
BINDING = "11111111-1111-1111-1111-111111111111"


class IsolationTests(TestCase):
    def test_plan_is_offline_and_run_scoped(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = drill.main(["plan", "--run-id", RUN_ID, "--fixture-image", IMAGE])
            self.assertEqual(result, 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["projects"], ["iso-" + RUN_ID + "-a", "iso-" + RUN_ID + "-b"])
            self.assertFalse(plan["mutates"])
            self.assertFalse((Path(temporary) / ".runtime").exists())

    def test_public_declarations_bind_distinct_scoped_projects(self):
        from app.spec import ApplicationEnvelopeV1Alpha2, to_flat
        for project in drill.project_names(RUN_ID):
            declaration = drill.declaration(project, IMAGE, RUN_ID, BINDING)
            ApplicationEnvelopeV1Alpha2.model_validate(declaration)
            flat = to_flat(declaration)
            self.assertEqual(flat["name"], project)
            self.assertEqual(flat["components"][0]["bindings"][0]["bindingId"], BINDING)
            self.assertEqual(flat["configuration"]["ACCEPTANCE_RUN_ID"], RUN_ID)
        with self.assertRaisesRegex(drill.DrillError, "invalid_fixture_project"):
            drill.declaration("smoke", IMAGE, RUN_ID, BINDING)

    def test_run_requires_exact_origin_confirmation(self):
        args = drill.parser().parse_args(["run", "--run-id", RUN_ID, "--fixture-image", IMAGE])
        with self.assertRaisesRegex(drill.DrillError, "explicit_environment_confirmation_required"):
            drill.validate(args)

    def test_uncertain_create_is_never_retired(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            report.data["createAttempted"].append(report.data["projects"][0])
            report.save()
            class API:
                def request(self, *args, **kwargs):
                    raise AssertionError("unproven project must not be queried or retired")
            drill.retire(API(), report)
            self.assertEqual(report.data["cleanup"], "incomplete-retry-required")
            self.assertEqual((report.directory / "report.json").stat().st_mode & 0o777, 0o600)

    def test_probe_rejects_unexpected_output_without_exposing_it(self):
        compile(drill.PROBE, "isolation-probe", "exec")
        class Result:
            returncode = 0
            stdout = '{"password": "secret"}'
            stderr = "another secret"
        with patch.object(drill.subprocess, "run", return_value=Result()) as process:
            with self.assertRaisesRegex(drill.DrillError, "invalid_probe_result"):
                drill.probe(Path("/tmp/kubectl"), Path("/tmp/kubeconfig"),
                            drill.project_names(RUN_ID)[0], "own", "foreign", "peer", "isolation")
        command = process.call_args.args[0]
        self.assertEqual(command[command.index("-n") + 1], "project-iso-" + RUN_ID + "-a")
