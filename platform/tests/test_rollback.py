import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rollback import dependency_report


class RollbackDependencyTests(unittest.TestCase):
    def test_report_never_claims_historical_secret_recovery(self):
        report = dependency_report({"configuration": {"MODE": "safe"}})
        self.assertEqual(report["database"], {"state": "retained", "rollback": "not_performed"})
        self.assertEqual(report["configuration"]["state"], "reapplied")
        self.assertEqual(report["application_secrets"]["state"], "current_only")
        self.assertNotIn("MODE", str(report))


if __name__ == "__main__":
    unittest.main()
