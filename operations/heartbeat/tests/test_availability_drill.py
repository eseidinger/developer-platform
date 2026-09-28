import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import call, patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "drill-platform-availability.py"
SPEC = importlib.util.spec_from_file_location("availability_drill", SCRIPT)
availability = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(availability)


class AvailabilityRecoveryTests(unittest.TestCase):
    @patch.object(availability, "command")
    def test_reconcile_preserves_volumes_and_starts_through_bootstrap(self, command):
        command.return_value = subprocess.CompletedProcess([], 0, "", "")

        availability.reconcile_platform("/opt/developer-platform", 600)

        self.assertEqual(command.call_args_list, [
            call("docker", "compose", "stop", "--timeout", "60", timeout=180,
                 cwd="/opt/developer-platform"),
            call("docker", "compose", "rm", "--force", timeout=180,
                 cwd="/opt/developer-platform"),
            call("bash", "scripts/up.sh", timeout=600,
                 cwd="/opt/developer-platform"),
        ])

    @patch.object(availability, "command")
    def test_postgres_health_requires_healthy_container(self, command):
        command.return_value = subprocess.CompletedProcess([], 0, "healthy\n", "")
        self.assertTrue(availability.postgres_healthy())

        command.return_value = subprocess.CompletedProcess([], 0, "starting\n", "")
        self.assertFalse(availability.postgres_healthy())

        command.return_value = subprocess.CompletedProcess([], 1, "", "")
        self.assertFalse(availability.postgres_healthy())

    @patch.object(availability.urllib.request, "urlopen")
    def test_api_readiness_requires_http_200(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.status = 200
        self.assertTrue(availability.url_ready("http://127.0.0.1:8000/readyz"))

        response.status = 503
        self.assertFalse(availability.url_ready("http://127.0.0.1:8000/readyz"))

        urlopen.side_effect = OSError("unavailable")
        self.assertFalse(availability.url_ready("http://127.0.0.1:8000/readyz"))


if __name__ == "__main__":
    unittest.main()
