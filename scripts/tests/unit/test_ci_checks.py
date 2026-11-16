"""CI must reject mismatched releases and missing required integration coverage."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


changes = module("ci_changes", "scripts/checks/ci-changes.py")
quality = module("ci_quality", "scripts/checks/check-quality.py")


class SelectionTests(unittest.TestCase):
    def test_pull_requests_compare_against_the_merge_base(self):
        with patch.object(
            changes.subprocess,
            "check_output",
            side_effect=["merge-base\n", b"platform/app/uv.lock\0"],
        ) as git:
            result = changes.selection(
                "pull_request", {"pull_request": {"base": {"sha": "base-sha"}}}
            )
        self.assertEqual(result["components"], "true")
        self.assertEqual(
            git.call_args_list[0].args[0], ["git", "merge-base", "base-sha", "HEAD"]
        )
        self.assertIn("merge-base", git.call_args_list[1].args[0])

    def test_document_changes_skip_components_but_shared_configuration_runs_them(self):
        event = {"before": "a" * 40, "ref": "refs/heads/main"}
        for paths, expected in (
            (b"docs/operators/a.md\0README.md\0", "false"),
            (b"platform/app/uv.lock\0", "true"),
            (b"docs/reference/platform-openapi.json\0", "true"),
            (b".github/workflows/ci.yaml\0", "true"),
            (b"scripts/tests/support/helper.py\0", "true"),
        ):
            with (
                self.subTest(paths=paths),
                patch.object(changes.subprocess, "check_output", return_value=paths),
            ):
                self.assertEqual(
                    changes.selection("push", event)["components"], expected
                )

    def test_tags_new_branches_manual_and_scheduled_runs_cannot_skip_components(self):
        for name, event in (
            ("push", {"ref": "refs/tags/v1.0.0", "before": "a" * 40}),
            ("push", {"before": "0" * 40}),
            ("schedule", {}),
            ("workflow_dispatch", {}),
        ):
            with (
                self.subTest(name=name),
                patch.object(changes.subprocess, "check_output") as git,
            ):
                self.assertEqual(changes.selection(name, event)["components"], "true")
                git.assert_not_called()

    def test_deleted_sources_still_trigger_component_checks(self):
        with patch.object(
            changes.subprocess,
            "check_output",
            return_value=b"platform/app/src/app/stores/s3.py\0",
        ):
            self.assertEqual(
                changes.selection("push", {"before": "a" * 40})["components"], "true"
            )

    def test_quality_scan_ignores_deleted_files_and_historical_documents(self):
        with patch.object(
            quality.subprocess,
            "check_output",
            return_value=b"README.md\0docs/history/adrs/old.md\0removed.py\0",
        ):
            self.assertEqual(quality.files("base"), ["README.md"])


class RequiredCoverageTests(unittest.TestCase):
    def test_skip_guard_changes_only_runs_that_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_prerequisite.py"
            path.write_text(
                "import pytest\n@pytest.mark.skip(reason='missing database')\ndef test_sql(): pass\n"
            )
            command = [
                sys.executable,
                "-m",
                "pytest",
                str(path),
                "-p",
                "tests.support.pytest_ci",
                "-q",
            ]
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            for extra, status in (([], 0), (["--fail-on-skip"], 1)):
                result = subprocess.run(
                    command + extra,
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    status,
                    result.stdout.decode() + result.stderr.decode(),
                )


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yaml").read_text())
        self.gate = self.workflow["jobs"]["required"]
        self.script = self.gate["steps"][0]["run"]
        self.results = {name: {"result": "success"} for name in self.gate["needs"]}
        self.results["changes"]["outputs"] = {"components": "true"}

    def evaluate(self):
        import json

        with patch.dict(os.environ, {"RESULTS": json.dumps(self.results)}):
            result = subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", self.script],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        if result.returncode:
            raise SystemExit(result.stderr)

    def test_every_ci_job_must_gate_publishing(self):
        self.assertEqual(
            set(self.gate["needs"]),
            set(self.workflow["jobs"]) - {"required"},
        )
        self.evaluate()

    def test_saved_logs_cannot_hide_component_test_failures(self):
        for path in (ROOT / ".github/workflows").glob("*.yaml"):
            workflow = yaml.safe_load(path.read_text())
            for job in workflow["jobs"].values():
                for step in job.get("steps", []):
                    if "tee " not in step.get("run", ""):
                        continue
                    # An explicit Bash shell makes GitHub enable pipefail;
                    # its implicit Bash invocation only guarantees errexit.
                    workflow_shell = (
                        workflow.get("defaults", {}).get("run", {}).get("shell")
                    )
                    job_shell = (
                        job.get("defaults", {})
                        .get("run", {})
                        .get("shell", workflow_shell)
                    )
                    shell = step.get("shell", job_shell)
                    with self.subTest(workflow=path.name, step=step.get("name")):
                        self.assertEqual(shell, "bash")

    def test_failure_cancellation_and_unexpected_skip_block_releases(self):
        for name in self.results:
            for status in ("failure", "cancelled", "skipped"):
                with self.subTest(name=name, status=status):
                    self.results[name]["result"] = status
                    with self.assertRaises(SystemExit):
                        self.evaluate()
                self.results[name]["result"] = "success"

    def test_documentation_skips_require_successful_selection_and_validation(self):
        self.results["changes"]["outputs"]["components"] = "false"
        for name in self.results:
            if name not in {"changes", "validate"}:
                self.results[name]["result"] = "skipped"
        self.evaluate()
        self.results["validate"]["result"] = "failure"
        with self.assertRaises(SystemExit):
            self.evaluate()
        self.results["validate"]["result"] = "success"
        self.results["changes"]["outputs"] = {}
        with self.assertRaises(SystemExit):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
