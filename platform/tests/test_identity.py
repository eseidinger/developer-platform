import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.identity import AuthenticationError, OIDCVerifier


class IdentityTests(unittest.TestCase):
    @patch("app.identity.PyJWKClient")
    @patch("app.identity.jwt.decode")
    def test_verifies_signature_issuer_audience_and_stable_subject(self, decode, jwk_client):
        jwk_client.return_value.get_signing_key_from_jwt.return_value = Mock(key="public-key")
        decode.return_value = {
            "iss": "https://issuer.example", "sub": "stable-subject", "exp": 2, "iat": 1,
            "preferred_username": "display-only",
        }
        principal = OIDCVerifier("https://issuer.example", "platform-api", "https://issuer.example/jwks").verify("token")
        self.assertEqual((principal.issuer, principal.subject, principal.display_name),
                         ("https://issuer.example", "stable-subject", "display-only"))
        self.assertEqual(decode.call_args.kwargs["audience"], "platform-api")
        self.assertEqual(decode.call_args.kwargs["issuer"], "https://issuer.example")

    @patch("app.identity.PyJWKClient")
    def test_rejects_a_token_without_a_subject(self, jwk_client):
        jwk_client.return_value.get_signing_key_from_jwt.return_value = Mock(key="public-key")
        with patch("app.identity.jwt.decode", return_value={"iss": "https://issuer.example", "exp": 2, "iat": 1}), \
                self.assertRaises(AuthenticationError):
            OIDCVerifier("https://issuer.example", "platform-api", "https://issuer.example/jwks").verify("token")
