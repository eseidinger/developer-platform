import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.audit import Actor, REDACTED, read_events, record_event, redact


class AuditTests(unittest.TestCase):
    def test_redact_removes_nested_credentials_and_bearer_values(self):
        value = redact({
            "password": "database-password",
            "nested": {"authorization": "Bearer should-not-appear"},
            "message": "token=should-not-appear, Bearer should-not-appear",
        })
        self.assertEqual(value["password"], REDACTED)
        self.assertEqual(value["nested"]["authorization"], REDACTED)
        self.assertNotIn("should-not-appear", value["message"])

    def test_record_event_uses_the_limited_writer_and_redacted_detail(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchone.return_value = (42,)
        with patch("app.audit.audit_connect", return_value=conn):
            event_id = record_event(
                Actor("oidc", "https://issuer.example|person-1"), "project.provision", "project", "demo",
                "succeeded", {"project": "demo"}, {"token": "should-not-appear"}, revision="r1",
            )
        self.assertEqual(event_id, 42)
        params = conn.execute.call_args.args[1]
        self.assertEqual(params[0:5], ("oidc", "https://issuer.example|person-1", "project.provision", "project", "demo"))
        self.assertEqual(params[-1].obj["token"], REDACTED)

    def test_read_events_uses_reader_and_redacts_legacy_values(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        occurred = datetime(2026, 10, 2, tzinfo=timezone.utc)
        conn.execute.return_value.fetchall.return_value = [
            (7, occurred, "oidc", "issuer|subject", "audit.export", "audit", None,
             {"project": "demo"}, "succeeded", None, None, {"token": "must-not-export"})
        ]
        with patch("app.audit.audit_reader_connect", return_value=conn):
            events = read_events(occurred, occurred, 10)
        self.assertEqual(events[0]["id"], 7)
        self.assertEqual(events[0]["occurred_at"], occurred.isoformat())
        self.assertEqual(events[0]["detail"]["token"], REDACTED)
        self.assertNotIn("must-not-export", str(events))
