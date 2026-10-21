"""Noninteractive runner renewal and target binding without contacting an issuer."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import jwt

from tests.platform.harness import API, DrillError, RunnerTokens, operator_tokens


class RunnerCredentialTests(unittest.TestCase):
    def payload(self):
        return {
            "platform_api_url": "http://127.0.0.1:8000",
            "platform_oidc_token_url": "https://identity.example/realms/platform/protocol/openid-connect/token",
            "platform_test_runner_client_id": "runner",
            "platform_test_runner_client_secret": "private-value",
            "platform_test_runner_credential_id": "credential-id",
            "platform_test_runner_expires_at": "2030-01-01T00:00:00Z",
        }

    def keycloak(self):
        return SimpleNamespace(
            issuer="https://identity.example/realms/platform", http=Mock()
        )

    def test_renewal_uses_client_credentials_and_reuses_valid_token(self):
        issuer = self.keycloak()
        token = jwt.encode({"exp": time.time() + 300}, "test-key-" * 8)
        issuer.http.post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": token}
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.json"
            path.write_text(json.dumps(self.payload()))
            path.chmod(0o600)
            tokens = operator_tokens(path, issuer)
        self.assertIsInstance(tokens, RunnerTokens)
        self.assertEqual(tokens.get(), token)
        self.assertEqual(tokens.get(), token)
        self.assertEqual(issuer.http.post.call_count, 1)
        self.assertEqual(
            issuer.http.post.call_args.kwargs["data"]["grant_type"],
            "client_credentials",
        )
        tokens.token = jwt.encode({"exp": time.time() - 1}, "test-key-" * 8)
        tokens.get()
        self.assertEqual(issuer.http.post.call_count, 2)

    def test_credential_cannot_be_sent_to_another_api_or_issuer(self):
        issuer = self.keycloak()
        tokens = RunnerTokens(self.payload(), issuer)
        with self.assertRaisesRegex(DrillError, "runner_api_mismatch"):
            API("http://127.0.0.1:9999", tokens)
        payload = self.payload()
        payload["platform_oidc_token_url"] = "https://other.example/token"
        with self.assertRaisesRegex(DrillError, "runner_token_endpoint_mismatch"):
            RunnerTokens(payload, issuer)
        issuer.http.post.assert_not_called()

    def test_failed_renewal_does_not_disclose_response_or_secret(self):
        issuer = self.keycloak()
        issuer.http.post.return_value = Mock(status_code=401, text="private-value")
        with self.assertRaisesRegex(DrillError, "^runner_token_unavailable$"):
            RunnerTokens(self.payload(), issuer).get()

    def test_credentials_must_be_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.json"
            path.write_text(json.dumps(self.payload()))
            path.chmod(0o644)
            with self.assertRaisesRegex(DrillError, "private_file_permissions"):
                operator_tokens(path, self.keycloak())
