"""The recovery credential must stay private and bound to the isolated guest."""

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
recovery_auth = importlib.import_module("recovery_auth")
access_token = recovery_auth.access_token


class RecoveryAuthTests(unittest.TestCase):
    def test_rejects_production_origin_before_using_client_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / ".runtime/recovery/test-runner.json"
            secret.parent.mkdir(parents=True)
            secret.write_text(
                json.dumps(
                    {
                        "platform_api_url": "https://platform.example.com",
                        "platform_oidc_token_url": "https://identity.example.com/token",
                        "platform_test_runner_client_id": "recovery-client",
                        "platform_test_runner_client_secret": "private-value",
                    }
                )
            )
            secret.chmod(0o600)
            with patch("recovery_auth.urllib.request.build_opener") as opener:
                with self.assertRaisesRegex(RuntimeError, "unexpected origin"):
                    access_token(root)
                opener.assert_not_called()

    def test_renews_only_against_the_private_guest_address(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "IDENTITY_DOMAIN=identity.localhost\nKEYCLOAK_IP=172.30.80.12\n"
            )
            secret = root / ".runtime/recovery/test-runner.json"
            secret.parent.mkdir(parents=True)
            secret.write_text(
                json.dumps(
                    {
                        "platform_api_url": "http://127.0.0.1:8000",
                        "platform_oidc_token_url": "https://identity.localhost/realms/platform/protocol/openid-connect/token",
                        "platform_test_runner_client_id": "recovery-client",
                        "platform_test_runner_client_secret": "private-value",
                    }
                )
            )
            secret.chmod(0o600)
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = b'{"access_token":"short-lived-token"}'
            with patch("recovery_auth.urllib.request.build_opener") as factory:
                factory.return_value.open.return_value = response
                self.assertEqual(access_token(root), "short-lived-token")
                request = factory.return_value.open.call_args.args[0]
                self.assertEqual(
                    request.full_url,
                    "http://172.30.80.12:8080/realms/platform/protocol/openid-connect/token",
                )
                self.assertNotIn("private-value", request.full_url)


if __name__ == "__main__":
    unittest.main()
