from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from app.stores.opensearch import OpenSearch, StoreError, index, role, tenant


class OpenSearchWorkspaceTests(TestCase):
    def setUp(self):
        self.resource = {"resource_id": str(uuid4())}
        self.other = {"resource_id": str(uuid4())}
        self.provider = OpenSearch("http://127.0.0.1:9200", "synthetic-password")
        self.provider.root = Mock()

    def test_exact_owned_layouts_are_selected_and_foreign_indexes_are_ignored(self):
        name = tenant(self.resource)
        owned = [
            ".kibana_-123_" + name,
            ".kibana_456_" + name + "_1",
            ".kibana_789_" + name + "_3.9.0_001",
        ]
        self.provider.root.request.return_value = [
            {"index": value, "store.size": "10"} for value in owned
        ] + [{"index": ".kibana_123_" + tenant(self.other) + "_1", "store.size": None}]
        self.assertEqual(
            self.provider.console_indices(self.resource),
            [(value, 10) for value in owned],
        )

    def test_unknown_owned_layout_fences_purge_before_any_destructive_operation(self):
        self.provider.root.request.return_value = [
            {"index": ".kibana_future_" + tenant(self.resource), "store.size": "10"}
        ]
        with self.assertRaises(StoreError):
            self.provider.purge(self.resource)
        self.assertTrue(
            all(
                call.args[0] == "GET"
                for call in self.provider.root.request.call_args_list
            )
        )

    def test_unknown_or_negative_console_size_does_not_underreport_resource_usage(self):
        for size in (None, "-1", "10kb"):
            self.provider.root.request.return_value = [
                {"index": ".kibana_123_" + tenant(self.resource), "store.size": size}
            ]
            with self.assertRaises(StoreError):
                self.provider.console_indices(self.resource)

    def test_resource_usage_includes_its_console_workspace(self):
        self.provider.root.request.side_effect = [
            {
                "indices": {
                    index(self.resource): {"total": {"store": {"size_in_bytes": 100}}}
                }
            },
            [
                {
                    "index": ".kibana_123_" + tenant(self.resource) + "_1",
                    "store.size": "20",
                }
            ],
        ]
        self.assertEqual(self.provider.usage(self.resource), 120)

    def test_human_console_issuance_requires_native_private_tenants_disabled(self):
        credential = {
            "credential_id": str(uuid4()),
            "mode": "read-only",
            "kind": "human",
        }
        native = Mock()
        self.provider.scoped = Mock(return_value=native)
        for value in (True, None):
            native.request.side_effect = [
                {"roles": [role(self.resource, "read-only")]},
                {"private_tenant_enabled": value},
            ]
            with self.assertRaises(StoreError):
                self.provider.verify_roles(self.resource, credential)
        native.request.side_effect = [
            {"roles": [role(self.resource, "read-only")]},
            {"private_tenant_enabled": False},
        ]
        self.provider.verify_roles(self.resource, credential)
