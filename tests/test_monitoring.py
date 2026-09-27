import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.monitoring import atomic_write, publish_catalog, reconcile, target_groups


class DiscoveryTests(unittest.TestCase):
    def test_active_and_failed_targets_retained_retired_removed(self):
        rows = [(name, {}, status) for name, status in
                [("ready", "applied"), ("broken", "failed"), ("new", "provisioning"), ("old", "retired")]]
        groups = target_groups(rows, "apps.example.com")
        self.assertEqual([g["labels"]["application"] for g in groups], ["broken", "new", "ready"])
        self.assertEqual(groups[0]["targets"], ["https://broken.apps.example.com/"])
        self.assertEqual(groups[0]["labels"]["probe_module"], "https_status")

    def test_local_routing_and_content_profile(self):
        group = target_groups([("smoke", {"probe_profile": "hello-world"}, "applied")], "apps.localhost")[0]
        self.assertEqual(group["targets"], ["http://proxy/"])
        self.assertEqual(group["labels"]["probe_hostname"], "smoke.apps.localhost")
        self.assertEqual(group["labels"]["instance"], "http://smoke.apps.localhost/")
        self.assertEqual(group["labels"]["probe_module"], "http_hello_world")

    def test_no_arbitrary_probe_destinations_or_modules(self):
        for domain in ("example.com/path", "localhost:123", "user@host", ""):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                target_groups([], domain)
        with self.assertRaises(ValueError):
            target_groups([("../evil", {}, "applied")], "apps.localhost")
        with self.assertRaises(ValueError):
            target_groups([("hello", {"probe_profile": "unknown"}, "applied")], "apps.localhost")

    def test_atomic_failure_preserves_previous_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "applications.json"
            atomic_write(path, "old")
            with patch("app.monitoring.os.replace", side_effect=OSError), self.assertRaises(OSError):
                atomic_write(path, "new")
            self.assertEqual(path.read_text(), "old")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_database_error_keeps_targets_and_freshness(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "MONITORING_DISCOVERY_DIR": directory, "APPS_DOMAIN": "apps.localhost"}):
            conn = Mock()
            conn.execute.return_value.fetchall.return_value = [("smoke", {}, "applied")]
            publish_catalog(conn)
            before = {p.name: p.read_text() for p in Path(directory).iterdir()}
            conn.execute.side_effect = RuntimeError("database unavailable")
            with self.assertRaises(RuntimeError):
                publish_catalog(conn)
            self.assertEqual(before, {p.name: p.read_text() for p in Path(directory).iterdir()})
            conn.execute.side_effect = None
            conn.execute.return_value.fetchall.return_value = [("smoke", {}, "retired")]
            publish_catalog(conn)
            self.assertEqual(json.loads((Path(directory) / "applications.json").read_text()), [])

    def test_busy_lifecycle_lock_leaves_publication_untouched(self):
        from unittest.mock import MagicMock
        connect = MagicMock()
        connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (False,)
        with patch("app.monitoring.publish_catalog") as publish:
            reconcile(connect)
            publish.assert_not_called()

    def test_reconcile_releases_lock_after_publication_failure(self):
        from unittest.mock import MagicMock
        connect = MagicMock()
        conn = connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = (True,)
        with patch("app.monitoring.publish_catalog", side_effect=OSError), self.assertRaises(OSError):
            reconcile(connect)
        self.assertIn("pg_advisory_unlock", conn.execute.call_args.args[0])

    def test_periodic_loop_retries_after_failure(self):
        from unittest.mock import Mock
        from app.monitoring import discovery_loop
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        log = Mock()
        with patch("app.monitoring.reconcile", side_effect=[OSError, None]) as attempt:
            discovery_loop(stop, Mock(), log)
        self.assertEqual(attempt.call_count, 2)
        self.assertEqual(stop.wait.call_count, 2)
        log.error.assert_called_once()
