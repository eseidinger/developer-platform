import sys
import unittest
import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.identity import Principal


def result(value):
    return Mock(fetchone=Mock(return_value=value))


class DataServiceTests(unittest.TestCase):
    principal = Principal("https://issuer.example", "person", "Person")
    timestamp = datetime(2026, 10, 5, tzinfo=timezone.utc)

    def test_reports_database_availability_without_credentials(self):
        conn = Mock()
        conn.execute.side_effect = [result((1,)), result((1,)), result(None)]
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=nullcontext(conn)):
            body = main.data_services("smoke", self.principal)
        self.assertEqual(body["services"], [{"type": "postgresql", "name": "managed", "state": "available", "reason": None}])
        self.assertIsNone(body["latest_recovery_request"])

    def test_creates_bounded_recovery_request(self):
        request_id = UUID(int=1)
        conn = Mock()
        conn.execute.side_effect = [result((1,)), result((request_id, "unavailable", "requested", self.timestamp, None))]
        with patch.object(main, "require_permission"), patch.object(main, "required_audit"), \
             patch.object(main, "uuid4", return_value=request_id), patch.object(main, "connect", return_value=nullcontext(conn)):
            body = main.request_data_service_recovery("smoke", main.DataServiceRecoveryRequest(reason="unavailable"), self.principal)
        self.assertEqual(body, {"project": "smoke", "request_id": str(request_id), "reason": "unavailable",
                                "status": "requested", "requested_at": self.timestamp.isoformat(), "reviewed_at": None})

    def test_operator_can_review_request(self):
        request_id = UUID(int=2)
        conn = Mock()
        conn.execute.return_value = result(("smoke", request_id, "access", "acknowledged", self.timestamp, self.timestamp))
        with patch.object(main, "require_platform_admin"), patch.object(main, "required_audit"), \
             patch.object(main, "connect", return_value=nullcontext(conn)):
            body = main.review_data_service_recovery_request(request_id, main.DataServiceRecoveryReview(status="acknowledged"), self.principal)
        self.assertEqual(body["status"], "acknowledged")
        self.assertEqual(body["project"], "smoke")

    def test_database_connection_failure_maps_to_a_safe_service_unavailable_response(self):
        response = asyncio.run(main.database_unavailable(Mock(), main.psycopg.OperationalError("sensitive detail")))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.body, b'{"detail":"Platform database is temporarily unavailable"}')


if __name__ == "__main__":
    unittest.main()
