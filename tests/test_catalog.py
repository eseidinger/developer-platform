import sys
import unittest
from contextlib import nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.catalog import initialize


class RecordingConnection:
    def __init__(self):
        self.statements = []
        self.transaction_started = False

    def transaction(self):
        self.transaction_started = True
        return nullcontext()

    def execute(self, statement, params=()):
        self.statements.append((statement, params))


class CatalogMigrationTests(unittest.TestCase):
    def test_migration_adds_stable_identity_and_versioned_lifecycle_tables_atomically(self):
        conn = RecordingConnection()
        initialize(conn)

        self.assertTrue(conn.transaction_started)
        statements = [statement for statement, _ in conn.statements]
        joined = "\n".join(statements)
        self.assertIn("UPDATE projects SET project_id=gen_random_uuid() WHERE project_id IS NULL", joined)
        self.assertIn("UNIQUE(project_id, name)", joined)
        self.assertIn("PRIMARY KEY(application_id, revision)", joined)
        self.assertIn("envelope_version SMALLINT NOT NULL CHECK (envelope_version > 0)", joined)
        self.assertIn("result_version SMALLINT CHECK (result_version > 0)", joined)
        self.assertIn("actor_issuer TEXT NOT NULL", joined)
        self.assertIn("actor_subject TEXT NOT NULL", joined)
        self.assertIn("ON CONFLICT(project_id, name) DO NOTHING", joined)
        self.assertIn("ON CONFLICT(application_id, revision) DO NOTHING", joined)
        self.assertEqual(statements[-1].lstrip().split()[0], "INSERT")


if __name__ == "__main__":
    unittest.main()
