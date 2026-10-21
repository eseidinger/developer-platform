import os
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from app.stores import providers


class ProviderSelectionTests(TestCase):
    def test_all_provider_quota_modes_are_available_to_resource_detail(self):
        from app.stores.neo4j import Neo4j
        from app.stores.opensearch import OpenSearch
        from app.stores.postgres import Postgres
        from app.stores.qdrant import Qdrant
        from app.stores.s3 import S3

        self.assertEqual(
            [
                kind.quota_enforcement
                for kind in (Postgres, S3, OpenSearch, Qdrant, Neo4j)
            ],
            [
                "advisory: PostgreSQL has no hard per-database byte quota",
                "hard",
                "advisory",
                "advisory",
                "advisory",
            ],
        )

    def test_default_has_only_postgresql_and_never_infers_other_services(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                [p["id"] for p in providers.availability() if p["enabled"]],
                ["postgresql"],
            )
            for name in ("s3", "qdrant", "opensearch", "neo4j"):
                with self.assertRaises(providers.ProviderUnavailable):
                    providers.get(name)

    def test_selection_requires_complete_operator_configuration_and_capacity(self):
        env = {
            "STORE_ENABLED_PROVIDERS": "postgresql,s3",
            "RUSTFS_IP": "172.30.80.16",
            "RUSTFS_ACCESS_KEY": "synthetic-access-key",
            "RUSTFS_SECRET_KEY": "s" * 32,
        }
        with patch.dict(os.environ, env, clear=True), patch("app.stores.s3.S3"):
            self.assertFalse(
                next(p for p in providers.availability() if p["id"] == "s3")["enabled"]
            )
            os.environ["RUSTFS_ACCESS_KEY"] = "k" * 20
            os.environ["STORE_CAPACITY_BYTES"] = (
                '{"postgresql":1073741824,"s3":1073741824}'
            )
            self.assertTrue(
                next(p for p in providers.availability() if p["id"] == "s3")["enabled"]
            )
            del os.environ["RUSTFS_SECRET_KEY"]
            with self.assertRaises(providers.ProviderUnavailable):
                providers.get("s3")

    def test_unsupported_edition_and_missing_ca_cannot_be_enabled_by_a_flag(self):
        env = {
            "STORE_ENABLED_PROVIDERS": "neo4j,opensearch",
            "OPENSEARCH_IP": "172.30.80.17",
            "OPENSEARCH_ADMIN_PASSWORD": "p" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            for name in ("neo4j", "opensearch"):
                with self.assertRaises(providers.ProviderUnavailable):
                    providers.get(name)

    def test_every_http_binding_points_to_its_lease_not_the_raw_service(self):
        for name, variable in [
            ("s3", "AWS_ENDPOINT_URL_S3"),
            ("opensearch", "OPENSEARCH_URL"),
            ("qdrant", "QDRANT_URL"),
        ]:
            backend = Mock()
            backend.credentials.return_value = {
                variable: "http://172.30.80.18:6333",
                "SCOPED_SECRET": "synthetic-secret",
            }
            with (
                self.subTest(provider=name),
                patch.object(providers, "get", return_value=backend),
                patch.dict(os.environ, {"STORE_RELAY_IP": "172.30.80.15"}),
            ):
                values = providers.connection(
                    {"provider": name, "resource_id": str(uuid4())},
                    {"relay_port": 20017},
                )
                self.assertEqual(values[variable], "http://172.30.80.15:20017")
                self.assertEqual(values["SCOPED_SECRET"], "synthetic-secret")
