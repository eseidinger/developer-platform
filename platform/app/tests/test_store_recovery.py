"""Old or incomplete recovery intent must not reach provider mutations."""

from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from app.stores import catalog, recovery


class StoreRecoveryTests(TestCase):
    def record(self):
        return {
            "resource_id": str(uuid4()),
            "owner_project": "alpha",
            "name": "state",
            "provider": "postgresql",
            "state": "active",
            "version": 3,
            "extensions": [],
            "quota_bytes": 1048576,
        }

    def test_missing_stale_or_foreign_manifest_fails_before_provider_access(self):
        stored = self.record()
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [(stored,)]
        for resources in (
            [],
            [{**stored, "version": 2}],
            [{**stored, "owner_project": "beta"}],
            [stored, self.record()],
        ):
            manifest = {
                "format": 1,
                "captured_at": "2026-10-17T12:00:00Z",
                "resources": resources,
            }
            with (
                self.subTest(resources=resources),
                patch.object(recovery, "required", return_value=True),
                patch("app.stores.providers.get") as provider,
                self.assertRaises(catalog.Conflict),
            ):
                recovery.reconcile(conn, manifest, apply=True)
            provider.assert_not_called()

    def test_duplicate_ids_and_injected_provider_fields_are_rejected(self):
        row = self.record()
        from pydantic import ValidationError

        for resources in ([row, row], [{**row, "endpoint": "http://foreign.invalid"}]):
            with self.assertRaises((ValueError, ValidationError)):
                recovery.validate_manifest(
                    {
                        "format": 1,
                        "captured_at": "2026-10-17T12:00:00Z",
                        "resources": resources,
                    }
                )
