import os
import unittest
from unittest.mock import MagicMock, patch

from app import catalog


class RetentionTests(unittest.TestCase):
    def test_nothing_is_pruned_within_the_window(self):
        conn = MagicMock()
        catalog.prune_revisions(conn, "app", 25, 25)
        conn.execute.assert_not_called()

    def test_prunes_operations_before_revisions_up_to_the_cutoff(self):
        conn = MagicMock()
        catalog.prune_revisions(conn, "app", 30, 25)
        first, second = [call.args for call in conn.execute.call_args_list]
        self.assertTrue(first[0].lstrip().startswith("DELETE FROM application_operations"))
        self.assertIn("'queued', 'running'", first[0])
        self.assertIn("operation_kind='restart'", first[0])
        self.assertEqual(first[1][:2], ("app", 5))
        self.assertTrue(second[0].lstrip().startswith("DELETE FROM application_revisions"))
        self.assertIn("NOT EXISTS", second[0])
        self.assertEqual(second[1], ("app", 5))

    def test_retention_setting(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REVISION_RETENTION", None)
            self.assertEqual(catalog.revision_retention(), 25)
        for value, expected in (("10", 10), ("0", 1), ("-3", 1), ("x", 25)):
            with patch.dict(os.environ, {"REVISION_RETENTION": value}):
                self.assertEqual(catalog.revision_retention(), expected)

    def test_new_revision_triggers_pruning(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [("env",), ("app",), (4, {"old": 1})]
        with patch.dict(os.environ, {"REVISION_RETENTION": "2"}):
            self.assertEqual(catalog.ensure_default_application(conn, "p", "n", {"new": 1}), ("app", 5))
        queries = [c.args[0].lstrip() for c in conn.execute.call_args_list]
        self.assertTrue(queries[-2].startswith("DELETE FROM application_operations"))
        self.assertEqual(conn.execute.call_args_list[-2].args[1][1], 3)
