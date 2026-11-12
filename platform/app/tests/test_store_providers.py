import os
from unittest import TestCase
from unittest.mock import Mock, patch

from app.stores import providers


class ProviderSelectionTests(TestCase):
    def test_default_advertises_only_postgresql_and_s3(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                [(item["id"], item["enabled"]) for item in providers.availability()],
                [("postgresql", True), ("s3", False)],
            )
            with self.assertRaises(providers.ProviderUnavailable):
                providers.get("s3")

    def test_s3_requires_selection_credentials_and_capacity(self):
        env = {
            "STORE_ENABLED_PROVIDERS": "postgresql,s3",
            "RUSTFS_IP": "172.30.80.16",
            "RUSTFS_ACCESS_KEY": "k" * 20,
            "RUSTFS_SECRET_KEY": "s" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(providers.availability()[1]["enabled"])
            os.environ["STORE_CAPACITY_BYTES"] = (
                '{"postgresql":1073741824,"s3":1073741824}'
            )
            self.assertTrue(providers.availability()[1]["enabled"])
            del os.environ["RUSTFS_SECRET_KEY"]
            with self.assertRaises(providers.ProviderUnavailable):
                providers.get("s3")

    def test_legacy_selection_cannot_reopen_native_providers(self):
        with patch.dict(
            os.environ,
            {"STORE_ENABLED_PROVIDERS": "postgresql,s3,qdrant,neo4j"},
            clear=True,
        ):
            for name in ("opensearch", "qdrant", "neo4j", "couchdb", "hugegraph"):
                with self.subTest(provider=name):
                    with self.assertRaises(providers.ProviderUnavailable):
                        providers.get(name)
                    self.assertEqual(providers.quota_enforcement(name), "advisory")

    def test_historical_neo4j_capabilities_remain_readable(self):
        capabilities = providers.capabilities("neo4j")
        self.assertTrue(capabilities["dedicated_instance"])
        self.assertEqual(capabilities["supported_modes"], ["read-write"])

    def test_postgresql_capabilities_advertise_reviewed_extensions(self):
        self.assertEqual(
            providers.capabilities("postgresql")["extensions"],
            ["vector", "age", "timescaledb", "postgis", "pgmq", "pg_duckdb"],
        )

    def test_s3_connection_uses_scoped_lease_relay(self):
        backend = Mock()
        backend.credentials.return_value = {"SCOPED_SECRET": "synthetic-secret"}
        with (
            patch.object(providers, "get", return_value=backend),
            patch.dict(os.environ, {"STORE_RELAY_IP": "172.30.80.15"}),
        ):
            fields = providers.connection({"provider": "s3"}, {"relay_port": 20017})
        self.assertEqual(fields["AWS_ENDPOINT_URL_S3"], "http://172.30.80.15:20017")
        self.assertEqual(fields["SCOPED_SECRET"], "synthetic-secret")
