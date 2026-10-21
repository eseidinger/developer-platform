"""Bindings inject only selected component credentials and private lease egress."""

import os
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from app.stores import catalog, workloads

from app import manifests


class ComponentStoreBindingTests(TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                "POSTGRES_IP": "172.30.80.10",
                "STORE_RELAY_IP": "172.30.80.15",
                "APPS_DOMAIN": "apps.localhost",
                "DATABASE_KEY": "fixture-only-key-" * 4,
            },
        )
        env.start()
        self.addCleanup(env.stop)
        guard = patch("app.stores.recovery.required", return_value=False)
        guard.start()
        self.addCleanup(guard.stop)
        self.grant_id, self.resource_id, self.credential_id = (
            str(uuid4()) for _ in range(3)
        )
        self.grant = {
            "grant_id": self.grant_id,
            "resource_id": self.resource_id,
            "kind": "binding",
            "consumer_project": "alpha",
            "component": "api",
            "state": "active",
            "mode": "read-write",
            "version": 1,
        }
        self.resource = {
            "resource_id": self.resource_id,
            "provider": "postgresql",
            "state": "active",
            "observed_state": "active",
            "extensions": [],
        }
        self.credential = {"credential_id": self.credential_id, "relay_port": 20000}
        self.conn = Mock()
        self.conn.execute.return_value.fetchone.return_value = (self.credential,)
        self.components = [
            {
                "name": name,
                "type": "service",
                "resolved_image": "docker.io/example/app@sha256:" + "a" * 64,
                "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                "exposure": "private",
                "replicas": 1,
                "bindings": [{"bindingId": self.grant_id}] if name == "api" else [],
            }
            for name in ("api", "worker")
        ]

    def attach(self, configuration=None):
        spec = {"name": "alpha", "components": self.components}
        rendered = manifests.component_resources(
            "alpha",
            self.components,
            "172.30.80.10",
            "LEGACY_SECRET_MUST_NOT_REACH_PODS",
            configuration,
            "apps.localhost",
        )
        with (
            patch.object(catalog, "grant", return_value=self.grant),
            patch.object(catalog, "resource", return_value=self.resource),
        ):
            return workloads.attach(self.conn, "alpha", spec, rendered)

    def test_unbound_component_receives_no_database_secret_or_private_store_egress(
        self,
    ):
        result = self.attach()
        self.assertNotIn("LEGACY_SECRET_MUST_NOT_REACH_PODS", str(result))
        secrets = [item for item in result if item["kind"] == "Secret"]
        self.assertEqual(len(secrets), 1)
        self.assertEqual(secrets[0]["stringData"]["PGHOST"], "172.30.80.15")
        self.assertEqual(secrets[0]["stringData"]["PGPORT"], "20000")
        self.assertEqual(
            secrets[0]["stringData"]["PGDATABASE"], catalog.identifier(self.resource_id)
        )
        for item in result:
            if item["kind"] == "Deployment":
                refs = [
                    ref["secretRef"]["name"]
                    for ref in item["spec"]["template"]["spec"]["containers"][0][
                        "envFrom"
                    ]
                ]
                self.assertNotIn("database", refs)
                self.assertEqual(
                    "store-" + self.grant_id in refs, item["metadata"]["name"] == "api"
                )
        policies = {
            item["metadata"]["name"]: item["spec"]
            for item in result
            if item["kind"] == "NetworkPolicy"
        }
        self.assertEqual(policies["store-worker"]["egress"], [])
        self.assertEqual(
            policies["store-api"]["podSelector"],
            {"matchLabels": {"platform.example/component": "api"}},
        )
        self.assertEqual(
            policies["store-api"]["egress"][0]["ports"],
            [{"protocol": "TCP", "port": 20000}],
        )
        self.assertNotIn("172.30.80.10/32", str(policies))

    def test_foreign_component_or_pending_binding_is_denied_before_render_application(
        self,
    ):
        for change in (
            {"component": "worker"},
            {"consumer_project": "beta"},
            {"state": "pending"},
        ):
            with (
                self.subTest(change=change),
                patch.dict(self.grant, change),
                self.assertRaises(catalog.Conflict),
            ):
                self.attach()

    def test_explicit_configuration_cannot_shadow_selected_binding_credentials(self):
        with self.assertRaises(catalog.Conflict):
            self.attach({"PGHOST": "shadowed"})
