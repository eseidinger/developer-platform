import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.identity import Principal


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class PlatformGrantApiTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("https://issuer.example", "admin", "Admin")

    def test_platform_administrator_can_list_platform_grants(self):
        granted_at = datetime(2026, 10, 7, tzinfo=timezone.utc)
        with patch.object(main, "require_platform_admin") as require_admin, \
             patch.object(main, "connect", return_value=Connection()), \
             patch.object(main, "grants_for_platform", return_value=[
                 ("https://issuer.example", "operator", "Operator", "platform-admin", granted_at)
             ]):
            body = main.get_platform_grants(self.principal)

        require_admin.assert_called_once_with(self.principal)
        self.assertEqual(body, {"grants": [{
            "issuer": "https://issuer.example", "subject": "operator", "display_name": "Operator",
            "role": "platform-admin", "granted_at": granted_at.isoformat(),
        }]})

    def test_platform_administrator_cannot_revoke_own_access(self):
        grant = main.GrantReference(issuer=self.principal.issuer, subject=self.principal.subject)
        with patch.object(main, "require_platform_admin"), patch.object(main, "required_audit"):
            with self.assertRaises(HTTPException) as raised:
                main.delete_platform_grant(grant, self.principal)

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
