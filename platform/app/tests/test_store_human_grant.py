"""Pasted grant identities must match the canonical token identity."""

from unittest import TestCase

from app.stores.contract import HumanGrant
from pydantic import ValidationError


class HumanGrantTests(TestCase):
    def test_clipboard_whitespace_is_removed_without_changing_identity(self):
        grant = HumanGrant(
            issuer=" \thttps://issuer.invalid/Realm\n",
            subject="\n Subject-ID \t",
            mode="read-write",
        )
        self.assertEqual(grant.issuer, "https://issuer.invalid/Realm")
        self.assertEqual(grant.subject, "Subject-ID")

    def test_blank_identities_are_rejected_after_trimming(self):
        for field in ("issuer", "subject"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                HumanGrant(
                    **{
                        "issuer": "https://issuer.invalid",
                        "subject": "user",
                        "mode": "read-only",
                        field: " \t\n",
                    }
                )
