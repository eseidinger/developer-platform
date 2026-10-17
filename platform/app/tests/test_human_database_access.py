import base64
import hashlib
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import human_database_access as access, main
from app.identity import Principal


def key() -> str:
    blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00 " + bytes(range(32))
    return "ssh-ed25519 " + base64.b64encode(blob).decode()


class HumanDatabaseAccessTests(unittest.TestCase):
    principal = Principal("https://issuer.example", "human", "Human")

    def test_key_is_strict_and_fingerprint_is_stable(self):
        normalized, fingerprint = access.parse_public_key(key())
        self.assertEqual(normalized, key())
        self.assertEqual(fingerprint, "SHA256:" + base64.b64encode(hashlib.sha256(
            base64.b64decode(key().split()[1])).digest()).decode().rstrip("="))
        for invalid in ("ssh-rsa AAAA", key() + " command=sh", "ssh-ed25519 !!!"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                access.parse_public_key(invalid)

    def test_role_names_are_separate_for_project_and_person(self):
        role = access.role_name("alpha", "issuer", "human")
        self.assertRegex(role, r"^human_[0-9a-f]{32}$")
        self.assertNotEqual(role, access.role_name("beta", "issuer", "human"))
        self.assertNotEqual(role, access.role_name("alpha", "issuer", "other"))

    def test_authorized_key_is_restricted_and_revoked_key_denied(self):
        _, fingerprint = access.parse_public_key(key())
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (key(), "alpha", "issuer", "human")
        result = access.authorized_key(conn, fingerprint, "172.30.80.10:5432")
        self.assertEqual(result[0], 'restrict,port-forwarding,permitopen="172.30.80.10:5432" ' + key())
        self.assertIn("AND active", conn.execute.call_args.args[0])
        conn.execute.return_value.fetchone.return_value = None
        self.assertIsNone(access.authorized_key(conn, fingerprint, "172.30.80.10:5432"))
        self.assertIsNone(access.authorized_key(conn, "invalid", "172.30.80.10:5432"))

    def test_revocation_disables_login_and_terminates_backends(self):
        conn = Mock()
        access.deny_role(conn, "human_abcd")
        self.assertIn("NOLOGIN PASSWORD NULL", str(conn.execute.call_args_list[0].args[0]))
        self.assertIn("pg_terminate_backend", conn.execute.call_args_list[1].args[0])
        self.assertEqual(conn.execute.call_args_list[1].args[1], ("human_abcd",))

    def test_legacy_issuance_cannot_bypass_named_resource_expiry(self):
        with patch.object(main, "connect") as connect:
            for action in (
                lambda: main.issue_my_human_database_credential("alpha", self.principal),
                lambda: main.grant_human_database_access("alpha", main.HumanDatabaseGrant(
                    issuer=self.principal.issuer, subject=self.principal.subject, public_key=key()), self.principal),
            ):
                with self.assertRaises(HTTPException) as error:
                    action()
                self.assertEqual(error.exception.status_code, 410)
            connect.assert_not_called()

    def test_automation_principal_cannot_use_human_database_flow(self):
        with patch.object(main, "connect", return_value=nullcontext(Mock())), \
             patch.object(main, "access_scope", return_value=object()), \
             patch.object(main, "required_audit") as audit:
            with self.assertRaises(HTTPException) as error:
                main.require_human_database_principal(self.principal, "alpha")
        self.assertEqual(error.exception.status_code, 403)
        audit.assert_called_once()

    def test_revoke_marks_grant_inactive_and_disables_role(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = ("human_abcd",)
        with patch.object(main, "require_permission"), \
             patch.object(main, "require_human_database_principal"), \
             patch.object(main, "connect", return_value=nullcontext(conn)), \
             patch.object(main.human_database_access, "deny_role") as deny, \
             patch.object(main, "required_audit"):
            result = main.revoke_human_database_access("alpha", main.HumanDatabaseReference(
                issuer=self.principal.issuer, subject=self.principal.subject), self.principal)
        self.assertEqual(result, {"project": "alpha", "revoked": True})
        self.assertIn("active=false", conn.execute.call_args.args[0])
        deny.assert_called_once_with(conn, "human_abcd")

    def test_tunnel_lookup_requires_separate_shared_token(self):
        with patch.dict(main.os.environ, {"DATABASE_BASTION_TOKEN": "a" * 64}), \
             patch.object(main, "connect") as connect:
            with self.assertRaises(HTTPException) as error:
                main.lookup_human_database_key("SHA256:" + "a" * 43, "wrong")
        self.assertEqual(error.exception.status_code, 404)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
