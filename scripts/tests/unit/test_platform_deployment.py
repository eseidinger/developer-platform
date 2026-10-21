"""Deployment ordering and refusal contracts; never invoke live deployment tools."""

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "platform_deployment", ROOT / "scripts/operations/deploy-platform.py"
)
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


class PlatformDeploymentTests(unittest.TestCase):
    def preflight_patches(self, command):
        self.enterContext(patch.object(deployment, "command", side_effect=command))
        self.enterContext(
            patch.object(deployment, "SYSTEMD", MagicMock(is_dir=lambda: True))
        )
        self.enterContext(
            patch.object(deployment.shutil, "which", return_value="fixture-tool")
        )

    def test_check_mode_cannot_stop_services_or_prepare_stores(self):
        calls = []
        self.preflight_patches(lambda args, **kwargs: calls.append(args) or "")
        deployment.deploy(check=True)
        self.assertTrue(any("--validate-networks" in args for args in calls))
        self.assertIn(
            [
                "findmnt",
                "--mountpoint",
                "/var/lib/developer-platform/tempo",
                "--noheadings",
            ],
            calls,
        )
        self.assertTrue(any(args[0] == "systemctl" for args in calls))
        self.assertFalse(
            any("stop" in args or "rm" in args or "bash" in args for args in calls)
        )
        self.assertFalse(
            any("scripts/setup/prepare-stores.py" in args for args in calls)
        )

    def test_maintenance_or_invalid_configuration_refuses_outage(self):
        for failure in ("maintenance", "configuration", "network", "mount"):
            calls = []

            def command(args, failure=failure, calls=calls, **kwargs):
                calls.append(args)
                if failure == "maintenance" and args[0] == "systemctl":
                    return "platform-backup.service loaded active running"
                if (
                    (
                        failure == "configuration"
                        and "scripts/setup/configure-platform.py" in args
                    )
                    or (failure == "network" and "--validate-networks" in args)
                    or (failure == "mount" and args[0] == "findmnt")
                ):
                    raise deployment.DeploymentError("fixture failure")
                return ""

            with (
                self.subTest(failure=failure),
                patch.object(deployment, "command", side_effect=command),
                patch.object(deployment, "SYSTEMD", MagicMock(is_dir=lambda: True)),
                patch.object(deployment.shutil, "which", return_value="fixture-tool"),
            ):
                with self.assertRaises(deployment.DeploymentError):
                    deployment.deploy()
                self.assertFalse(any("stop" in args or "rm" in args for args in calls))

    def test_store_preparation_then_stop_remove_bootstrap_and_readiness(self):
        calls = []
        self.preflight_patches(lambda args, **kwargs: calls.append(args) or "")
        with patch.object(
            deployment,
            "wait_for_api",
            side_effect=lambda timeout: calls.append(["ready", timeout]),
        ):
            deployment.deploy(readiness_timeout=15)
        prepare = next(
            i
            for i, args in enumerate(calls)
            if "scripts/setup/prepare-stores.py" in args
        )
        stop = calls.index(["docker", "compose", "stop", "--timeout", "60"])
        remove = calls.index(["docker", "compose", "rm", "--force"])
        bootstrap = calls.index(["bash", "scripts/up.sh"])
        self.assertLess(prepare, stop)
        self.assertLess(stop, remove)
        self.assertLess(remove, bootstrap)
        self.assertLess(bootstrap, calls.index(["ready", 15]))
        self.assertFalse(any("down" in args or "--volumes" in args for args in calls))

    def test_failed_store_preparation_does_not_stop_services(self):
        calls = []

        def command(args, **kwargs):
            calls.append(args)
            if "scripts/setup/prepare-stores.py" in args:
                raise deployment.DeploymentError("fixture failure")
            return ""

        self.preflight_patches(command)
        with self.assertRaises(deployment.DeploymentError):
            deployment.deploy()
        self.assertFalse(any("stop" in args for args in calls))

    def test_private_command_failure_does_not_expose_diagnostics(self):
        with (
            patch.object(
                deployment.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    [], 1, "fixture-secret", "private-diagnostics"
                ),
            ),
            self.assertRaises(deployment.DeploymentError) as raised,
        ):
            deployment.command(["fixture-tool"], private=True)
        self.assertNotIn("fixture-secret", str(raised.exception))
        self.assertNotIn("private-diagnostics", str(raised.exception))

    def test_local_startup_does_not_invoke_disruptive_deployment(self):
        source = (ROOT / "scripts/up.sh").read_text()
        self.assertIn("scripts/setup/configure-platform.py --runtime", source)
        self.assertNotIn("deploy-platform.py", source)
        self.assertNotIn("docker compose stop", source)
        self.assertNotIn("docker compose rm", source)

    def test_readiness_retries_then_succeeds_without_a_live_api(self):
        opener = MagicMock()
        ready = MagicMock()
        ready.__enter__.return_value.status = 200
        opener.open.side_effect = [deployment.urllib.error.URLError("offline"), ready]
        with (
            patch.object(
                deployment.urllib.request, "build_opener", return_value=opener
            ),
            patch.object(deployment.time, "sleep") as sleep,
        ):
            deployment.wait_for_api(15)
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once()

    def test_readiness_timeout_is_a_deployment_failure(self):
        opener = MagicMock()
        opener.open.side_effect = deployment.urllib.error.URLError("offline")
        with (
            patch.object(
                deployment.urllib.request, "build_opener", return_value=opener
            ),
            patch.object(deployment.time, "monotonic", side_effect=[0, 6]),
            self.assertRaisesRegex(deployment.DeploymentError, "readiness timed out"),
        ):
            deployment.wait_for_api(5)


if __name__ == "__main__":
    unittest.main()
