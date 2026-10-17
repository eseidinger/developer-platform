import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import retirement_access_inventory
from app.retirement import scope_token


class RetirementAccessInventoryTests(unittest.TestCase):
    def test_inventory_contains_only_role_and_lifecycle_counts(self):
        conn = Mock()
        conn.execute.side_effect = [Mock(fetchall=Mock(return_value=[("developer", 2), ("viewer", 1)])),
                                    Mock(fetchall=Mock(return_value=[("active", 1), ("revocation_pending", 2)])),
                                    Mock(fetchall=Mock(return_value=[("resource-id", "orders", "postgresql", "active", 1)])),
                                    Mock(fetchall=Mock(return_value=[("grant-id", "resource-id", "binding", "read-write", "active", 2, "shop", "api")]))]
        inventory = retirement_access_inventory(conn, "shop")
        self.assertEqual(inventory, {"grants_by_role": {"developer": 2, "viewer": 1},
                                     "credentials_by_status": {"active": 1, "revocation_pending": 2},
                                     "named_store_resources": [{"resource_id": "resource-id", "name": "orders", "provider": "postgresql", "state": "active", "version": 1}],
                                     "named_store_grants": [{"grant_id": "grant-id", "resource_id": "resource-id", "kind": "binding", "mode": "read-write", "state": "active", "version": 2, "consumer_project": "shop", "component": "api"}]})
        self.assertNotIn("subject", str(inventory))
        self.assertNotEqual(scope_token("shop", 3, inventory), scope_token("shop", 3, {}))
        previous = scope_token("shop", 3, inventory)
        inventory["named_store_resources"][0]["version"] = 2
        self.assertNotEqual(previous, scope_token("shop", 3, inventory))


if __name__ == "__main__":
    unittest.main()
