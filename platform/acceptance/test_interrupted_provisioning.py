"""Offline outage safety and named-binding contract for the interruption drill."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app/src"))
from acceptance import interrupted_provisioning as drill

RUN_ID = "0123456789ab"
IMAGE = "docker.io/example/web-postgres@sha256:" + "a" * 64
BINDING = "11111111-1111-1111-1111-111111111111"


class InterruptedProvisioningTests(TestCase):
    def test_plan_is_offline_and_discloses_outage(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = drill.main(["plan", "--run-id", RUN_ID, "--fixture-image", IMAGE])
            plan = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertFalse(plan["mutates"])
            self.assertTrue(plan["requiresIdleLab"])
            self.assertIn("kill platform-api", plan["outage"])
            self.assertFalse((Path(temporary) / ".runtime").exists())

    def test_run_requires_exact_outage_confirmation(self):
        args = drill.parser().parse_args(["run", "--run-id", RUN_ID, "--fixture-image", IMAGE,
            "--confirm-environment", "http://127.0.0.1:8000", "--operator-token-file", "/tmp/session"])
        with self.assertRaisesRegex(drill.DrillError, "explicit_outage_confirmation_required"):
            drill.validate(args)
        args.confirm_outage = drill.OUTAGE_CONFIRMATION
        drill.validate(args)

    def test_declaration_uses_current_named_binding(self):
        from app.spec import ApplicationEnvelopeV1Alpha2, to_flat
        project = drill.project_name(RUN_ID)
        declaration = drill.declaration(project, IMAGE, RUN_ID, BINDING, "600m")
        ApplicationEnvelopeV1Alpha2.model_validate(declaration)
        flat = to_flat(declaration)
        self.assertEqual(flat["components"][0]["bindings"][0]["bindingId"], BINDING)
        self.assertEqual(flat["configuration"]["ACCEPTANCE_RUN_ID"], RUN_ID)
        self.assertEqual(flat["components"][0]["resources"]["limits"]["cpu"], "600m")

    def test_host_restore_attempts_both_services_after_first_failure(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            calls = []
            def command(args, **kwargs):
                calls.append(args)
                if args[1] == "unpause":
                    raise drill.DrillError("host_command_failed")
            with patch.object(drill, "command", side_effect=command):
                with self.assertRaisesRegex(drill.DrillError, "host_restore_failed"):
                    drill.restore_host(report)
            self.assertEqual([call[1] for call in calls], ["unpause", "compose"])
            self.assertEqual(report.data["outage"], "restore-failed-manual-action-required")

    def test_failed_put_after_pause_still_restores_host(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            report.data["bindingId"] = BINDING
            calls = []
            def command(args, **kwargs):
                calls.append(args)
            class API:
                def request(self, *args, **kwargs):
                    raise drill.DrillError("control_api_http_503")
            args = SimpleNamespace(run_id=RUN_ID, fixture_image=IMAGE)
            with patch.object(drill, "command", side_effect=command):
                with self.assertRaisesRegex(drill.DrillError, "control_api_http_503"):
                    drill.interrupt(args, API(), report, 1)
            self.assertEqual([call[1] for call in calls], ["pause", "unpause", "compose"])
            self.assertEqual(report.data["outage"], "restored")

    def test_uncertain_create_never_auto_retires_project(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(drill, "ROOT", Path(temporary)):
            report = drill.Report(RUN_ID, "http://127.0.0.1:8000", IMAGE)
            report.data["projectCreateAttempted"] = True
            class API:
                def request(self, *args, **kwargs):
                    raise AssertionError("unproven project must not be queried")
            drill.retire(API(), report)
            self.assertEqual(report.data["cleanup"], "incomplete-retry-required")

    def test_preflight_rejects_enabled_admission_before_host_commands(self):
        class API:
            def request(self, *args, **kwargs):
                raise AssertionError("API must not be queried")
        with patch.object(drill, "command") as host:
            with self.assertRaisesRegex(drill.DrillError, "capacity_admission_must_be_disabled"):
                drill.host_preflight({"CAPACITY_ADMISSION_ENABLED": "true"}, API(), None, None)
        host.assert_not_called()
