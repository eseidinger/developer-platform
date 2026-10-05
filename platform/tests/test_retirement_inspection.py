import sys
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.identity import Principal


class RetirementInspectionTests(unittest.TestCase):
    def test_operator_inspection_returns_retained_inventory_and_cleanup_counts(self):
        conn = Mock()
        conn.execute.side_effect = [Mock(fetchone=Mock(return_value=("retired", datetime(2026, 10, 5, tzinfo=timezone.utc), {"database": "project_shop"}))),
                                    Mock(fetchall=Mock(return_value=[])), Mock(fetchall=Mock(return_value=[("revocation_pending", 1)]))]
        principal = Principal("https://issuer.example", "operator", "Operator")
        with patch.object(main, "require_platform_admin"), patch.object(main, "required_audit"), patch.object(main, "connect", return_value=nullcontext(conn)):
            result = main.inspect_retirement("shop", principal)
        self.assertEqual(result["retained"], {"database": "project_shop"})
        self.assertEqual(result["credential_cleanup"], {"revocation_pending": 1})


if __name__ == "__main__":
    unittest.main()
