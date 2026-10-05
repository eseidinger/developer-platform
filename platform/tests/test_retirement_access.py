import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import retirement_access_inventory
from app.retirement import scope_token


class RetirementAccessInventoryTests(unittest.TestCase):
    def test_inventory_contains_only_role_and_lifecycle_counts(self):
        conn = Mock()
        conn.execute.side_effect = [Mock(fetchall=Mock(return_value=[("developer", 2), ("viewer", 1)])),
                                    Mock(fetchall=Mock(return_value=[("active", 1), ("revocation_pending", 2)]))]
        inventory = retirement_access_inventory(conn, "shop")
        self.assertEqual(inventory, {"grants_by_role": {"developer": 2, "viewer": 1},
                                     "credentials_by_status": {"active": 1, "revocation_pending": 2}})
        self.assertNotIn("subject", str(inventory))
        self.assertNotEqual(scope_token("shop", 3, inventory), scope_token("shop", 3, {}))


if __name__ == "__main__":
    unittest.main()
