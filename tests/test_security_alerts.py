import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.security_alerts import publish, render, security_event_rows


class SecurityAlertTests(unittest.TestCase):
    def test_query_classifies_only_security_relevant_audit_events(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        security_event_rows(conn)
        query = conn.execute.call_args.args[0]
        self.assertIn("authentication_failure", query)
        self.assertIn("access_denial", query)
        self.assertIn("privileged_change", query)
        self.assertIn("membership.%%", query)
        self.assertIn("make_interval", query)

    def test_render_uses_resource_labels_not_actor_or_event_detail(self):
        text = render([
            ("access_denial", "project", "demo", "demo", 5, 42, 1700000000),
        ], now=1700000010)
        self.assertIn('category="access_denial"', text)
        self.assertIn('target_id="demo"', text)
        self.assertIn("platform_security_latest_event_id", text)
        self.assertNotIn("actor", text)

    def test_publish_does_not_replace_previous_metrics_after_reader_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "security-events.prom"
            target.write_text("previous\n")
            with patch("app.security_alerts.audit_reader_connect", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    publish(directory, now=1)
            self.assertEqual(target.read_text(), "previous\n")
