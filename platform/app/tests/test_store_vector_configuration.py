from unittest import TestCase

from app.stores import recovery
from app.stores.contract import ResourceCreate, StoredResourceConfiguration
from pydantic import ValidationError


class VectorConfigurationTests(TestCase):
    def test_vector_schema_is_bounded_and_provider_specific(self):
        for provider, configuration in [
            ("postgresql", {"vector_size": 4}),
            ("qdrant", {"vector_size": 0}),
            ("qdrant", {"vector_size": 65537}),
            ("qdrant", {"endpoint": "http://injected.invalid"}),
            ("qdrant", {"distance": "unsupported"}),
        ]:
            with (
                self.subTest(provider=provider, configuration=configuration),
                self.assertRaises(ValidationError),
            ):
                StoredResourceConfiguration(
                    name="vectors", provider=provider, configuration=configuration
                )
        body = StoredResourceConfiguration(
            name="vectors",
            provider="qdrant",
            configuration={"vector_size": 4, "distance": "Dot"},
        )
        self.assertEqual(
            body.configuration.model_dump(), {"vector_size": 4, "distance": "Dot"}
        )

    def test_new_resources_reject_legacy_providers(self):
        for provider in ("qdrant", "opensearch", "neo4j", "couchdb", "hugegraph"):
            with self.subTest(provider=provider), self.assertRaises(ValidationError):
                ResourceCreate(name="legacy", provider=provider)
        self.assertEqual(
            ResourceCreate(name="db", provider="postgresql").extensions, []
        )
        self.assertEqual(ResourceCreate(name="objects", provider="s3").provider, "s3")

    def test_postgresql_extensions_are_unique_and_provider_specific(self):
        supported = [
            "vector",
            "age",
            "timescaledb",
            "postgis",
            "pgmq",
            "pg_duckdb",
        ]
        self.assertEqual(
            ResourceCreate(
                name="analytics", provider="postgresql", extensions=supported
            ).extensions,
            supported,
        )
        for provider, extensions in (
            ("postgresql", ["postgis", "postgis"]),
            ("postgresql", ["unreviewed"]),
            ("s3", ["pgmq"]),
        ):
            with (
                self.subTest(provider=provider, extensions=extensions),
                self.assertRaises(ValidationError),
            ):
                ResourceCreate(name="invalid", provider=provider, extensions=extensions)

    def test_recovery_preserves_and_validates_the_vector_schema(self):
        from uuid import uuid4

        row = {
            "resource_id": str(uuid4()),
            "owner_project": "alpha",
            "name": "vectors",
            "provider": "qdrant",
            "state": "active",
            "version": 1,
            "quota_bytes": 1048576,
            "extensions": [],
            "configuration": {"vector_size": 4, "distance": "Dot"},
        }
        manifest = {
            "format": 1,
            "captured_at": "2026-10-17T12:00:00Z",
            "resources": [row],
        }
        self.assertEqual(
            recovery.validate_manifest(manifest)["resources"][0]["configuration"],
            row["configuration"],
        )
        row["configuration"] = {"endpoint": "http://injected.invalid"}
        with self.assertRaises(ValidationError):
            recovery.validate_manifest(manifest)
