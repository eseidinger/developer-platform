"""Initial administrator creation preserves credentials and requires a password change."""

import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_local_admin", ROOT / "scripts/setup/bootstrap-local-admin.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def response(value, headers=None):
    result = io.BytesIO(json.dumps(value).encode())
    result.headers = headers or {}
    return result


class LocalAdminBootstrapTests(unittest.TestCase):
    def root(self, directory):
        root = Path(directory)
        (root / ".env").write_text(
            "KEYCLOAK_ADMIN_PASSWORD=private-admin\nIDENTITY_DOMAIN=identity.localhost\n"
        )
        return root

    def test_temporary_password_is_private_and_bootstrap_uses_immutable_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            output = root / "private" / "initial-admin.json"
            opener = Mock()
            opener.open.side_effect = [
                response({"access_token": "admin-token"}),
                response([]),
                response({}, {"Location": "http://keycloak/users/subject-id"}),
            ]
            with (
                patch.object(
                    bootstrap.urllib.request, "build_opener", return_value=opener
                ),
                patch.object(bootstrap, "configure") as configure,
            ):
                self.assertEqual(
                    bootstrap.create_admin(root, "person", output), "subject-id"
                )
            payload = json.loads(opener.open.call_args.args[0].data)
            self.assertEqual(payload["username"], "person")
            self.assertTrue(payload["credentials"][0]["temporary"])
            self.assertEqual(payload["requiredActions"], ["UPDATE_PASSWORD"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                json.loads(output.read_text())["temporary_password"],
                payload["credentials"][0]["value"],
            )
            configure.assert_called_once_with(
                root, {"options": {"bootstrap_subject": "subject-id"}}
            )

    def test_existing_account_is_never_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            output = root / "initial-admin.json"
            opener = Mock()
            opener.open.side_effect = [
                response({"access_token": "admin-token"}),
                response([{"id": "existing"}]),
            ]
            with (
                patch.object(
                    bootstrap.urllib.request, "build_opener", return_value=opener
                ),
                self.assertRaises(ValueError),
            ):
                bootstrap.create_admin(root, "person", output)
            self.assertEqual(opener.open.call_count, 2)
            self.assertFalse(output.exists())

    def test_lost_create_response_preserves_the_private_recovery_password(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            output = root / "initial-admin.json"
            opener = Mock()
            opener.open.side_effect = [
                response({"access_token": "admin-token"}),
                response([]),
                urllib.error.URLError("lost"),
            ]
            with (
                patch.object(
                    bootstrap.urllib.request, "build_opener", return_value=opener
                ),
                self.assertRaises(urllib.error.URLError),
            ):
                bootstrap.create_admin(root, "person", output)
            self.assertEqual(
                json.loads(output.read_text())["status"], "creation-pending"
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
