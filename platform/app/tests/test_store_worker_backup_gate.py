"""Protect retained Phase 8 stores from purge before backup verification."""

from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from app.stores import worker


class PhaseEightPurgeGateTests(TestCase):
    def reconcile_resource(self, resource, held_credentials=False):
        connection = MagicMock()
        provider = Mock()

        def execute(statement, *_arguments):
            result = Mock()
            result.fetchall.return_value = []
            result.fetchone.return_value = None
            if (
                "FROM store_resources r" in statement
                and "observed_state<>state" in statement
            ):
                result.fetchall.return_value = [(resource,)]
            if (
                held_credentials
                and "SELECT 1 FROM store_credentials c JOIN store_grants g" in statement
            ):
                result.fetchone.return_value = (1,)
            return result

        connection.execute.side_effect = execute
        with (
            patch.object(worker.recovery, "required", return_value=False),
            patch.object(worker.providers, "get", return_value=provider),
        ):
            worker.reconcile(connection)
        return connection, provider

    def resource(self, provider, backup_version=None, snapshot=None):
        return {
            "resource_id": str(uuid4()),
            "provider": provider,
            "state": "purging",
            "version": 7,
            "purge_backup_version": backup_version,
            "purge_backup_snapshot": snapshot,
        }

    def test_missing_or_stale_backup_keeps_phase_eight_data(self):
        for provider_name in ("couchdb", "hugegraph"):
            for backup_version, snapshot in ((None, None), (6, "old"), (7, None)):
                with self.subTest(
                    provider=provider_name,
                    backup_version=backup_version,
                    snapshot=snapshot,
                ):
                    resource = self.resource(provider_name, backup_version, snapshot)
                    connection, provider = self.reconcile_resource(resource)

                    provider.purge.assert_not_called()
                    self.assertTrue(
                        any(
                            "PurgeAwaitingVerifiedBackup" in call.args[0]
                            and call.args[1] == (resource["resource_id"],)
                            for call in connection.execute.call_args_list
                        )
                    )
                    self.assertFalse(
                        any(
                            "SET state=%s,observed_state=%s" in call.args[0]
                            for call in connection.execute.call_args_list
                        )
                    )

    def test_matching_backup_allows_phase_eight_provider_purge(self):
        for provider_name in ("couchdb", "hugegraph"):
            with self.subTest(provider=provider_name):
                resource = self.resource(provider_name, 7, "verified-snapshot")
                connection, provider = self.reconcile_resource(resource)

                provider.purge.assert_called_once_with(resource)
                self.assertTrue(
                    any(
                        "SET state=%s,observed_state=%s" in call.args[0]
                        and call.args[1]
                        == ("purged", "purged", resource["resource_id"])
                        for call in connection.execute.call_args_list
                    )
                )

    def test_active_credentials_block_purge_even_with_matching_backup(self):
        for provider_name in ("couchdb", "hugegraph"):
            with self.subTest(provider=provider_name):
                resource = self.resource(provider_name, 7, "verified-snapshot")
                connection, provider = self.reconcile_resource(
                    resource, held_credentials=True
                )

                provider.purge.assert_not_called()
                self.assertFalse(
                    any(
                        "SET state=%s,observed_state=%s" in call.args[0]
                        for call in connection.execute.call_args_list
                    )
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
