"""Boundary evidence must distinguish credential expiry from an expired JWT."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts.tests.support.runner_expiry import ExpiryError, verify


class ExpiryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "evidence.json"
        self.payload = {
            "phase": "active",
            "api": "http://127.0.0.1:8000",
            "token_url": "https://identity.invalid/token",
            "client_id": "runner",
            "client_secret": "synthetic",
            "credential_id": "fixture",
            "expires_at": "1970-01-01T00:01:40+00:00",
            "state_file": str(self.path),
        }
        claims = (
            base64.urlsafe_b64encode(json.dumps({"exp": 200}).encode())
            .decode()
            .rstrip("=")
        )
        self.bearer = "header." + claims + ".signature"

    def active(self):
        call = Mock(side_effect=[(200, {"access_token": self.bearer}), (200, [])])
        verify(self.payload, call=call, now=lambda: 90)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_expired_credential_denied_with_still_valid_held_token(self):
        self.active()
        self.payload["phase"] = "expired"
        call = Mock(side_effect=[(401, {"error": "invalid_client"}), (403, {})])
        result = verify(self.payload, call=call, now=lambda: 101)
        self.assertEqual(result["result"], "passed")
        self.assertEqual(call.call_args.kwargs["token"], self.bearer)

    def test_wrong_secret_cannot_masquerade_as_expiry(self):
        self.active()
        self.payload.update(phase="expired", client_secret="wrong")
        call = Mock()
        with self.assertRaisesRegex(ExpiryError, "identity_mismatch"):
            verify(self.payload, call=call, now=lambda: 101)
        call.assert_not_called()

    def test_expired_jwt_cannot_prove_credential_enforcement(self):
        self.active()
        self.payload["phase"] = "expired"
        with self.assertRaisesRegex(ExpiryError, "held_jwt_already_expired"):
            verify(self.payload, call=Mock(), now=lambda: 201)

    def test_active_must_be_close_enough_to_credential_expiry(self):
        self.payload["expires_at"] = "1970-01-01T00:05:00+00:00"
        call = Mock(return_value=(200, {"access_token": self.bearer}))
        with self.assertRaisesRegex(ExpiryError, "run_active_near_expiry"):
            verify(self.payload, call=call, now=lambda: 90)
        self.assertFalse(self.path.exists())

    def test_held_token_still_accepted_after_credential_expiry_is_failure(self):
        self.active()
        self.payload["phase"] = "expired"
        call = Mock(side_effect=[(401, {"error": "invalid_client"}), (200, [])])
        with self.assertRaisesRegex(ExpiryError, "held_unexpired_jwt_not_denied"):
            verify(self.payload, call=call, now=lambda: 101)


if __name__ == "__main__":
    unittest.main()
