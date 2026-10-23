"""Certificate creation alone does not establish a healthy gateway listener."""

import importlib.util
import ssl
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "local_https_fixture",
    ROOT / "scripts/tests/components/networking/verify-local-https.py",
)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class GatewayReadinessTests(unittest.TestCase):
    def wait(self, request):
        elapsed = [0.0]

        def advance(seconds):
            elapsed[0] += seconds

        fixture.wait_ready(
            request,
            "identity.localhost",
            "/ready",
            seconds=1,
            clock=lambda: elapsed[0],
            sleep=advance,
        )

    def test_listener_reset_and_upstream_startup_wait_for_a_real_success(self):
        request = Mock(side_effect=[ConnectionResetError(), 502, 200])
        self.wait(request)
        self.assertEqual(request.call_count, 3)
        request.assert_called_with("identity.localhost", "/ready")

    def test_wrong_route_or_untrusted_certificate_never_establish_readiness(self):
        for request in (
            Mock(return_value=404),
            Mock(side_effect=ssl.SSLCertVerificationError("untrusted test CA")),
        ):
            with self.assertRaisesRegex(AssertionError, "verified HTTPS readiness"):
                self.wait(request)
