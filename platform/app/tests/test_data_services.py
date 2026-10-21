import asyncio
import sys
import unittest
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.identity import Principal
from fastapi import HTTPException

from app import main


def result(value):
    return Mock(fetchone=Mock(return_value=value))


class DataServiceTests(unittest.TestCase):
    principal = Principal("https://issuer.example", "person", "Person")
    timestamp = datetime(2026, 10, 5, tzinfo=UTC)

    def test_reports_named_resources_and_bindings_without_credentials(self):
        conn = Mock()
        conn.execute.side_effect = [
            result((1,)),
            Mock(
                fetchall=Mock(
                    return_value=[
                        (
                            "resource-id",
                            "smoke",
                            "primary",
                            "postgresql",
                            "active",
                            "active",
                            None,
                        )
                    ]
                )
            ),
            Mock(
                fetchall=Mock(
                    return_value=[
                        (
                            "binding-id",
                            "resource-id",
                            "web",
                            "active",
                            "active",
                            None,
                            True,
                        )
                    ]
                )
            ),
            result(None),
        ]
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=nullcontext(conn)),
        ):
            body = main.data_services("smoke", self.principal)
        self.assertEqual(
            body["services"],
            [
                {
                    "resource_id": "resource-id",
                    "owner_project": "smoke",
                    "type": "postgresql",
                    "name": "primary",
                    "state": "available",
                    "observed_state": "active",
                    "reason": None,
                }
            ],
        )
        self.assertEqual(
            body["bindings"],
            [
                {
                    "binding_id": "binding-id",
                    "resource_id": "resource-id",
                    "component": "web",
                    "state": "active",
                    "observed_state": "active",
                    "reason": None,
                    "credential_active": True,
                }
            ],
        )
        self.assertIsNone(body["latest_recovery_request"])
        self.assertFalse(
            any("pg_database" in call.args[0] for call in conn.execute.call_args_list)
        )

    def test_empty_project_has_no_implicit_database_or_bindings(self):
        conn = Mock()
        conn.execute.side_effect = [
            result((1,)),
            Mock(fetchall=Mock(return_value=[])),
            Mock(fetchall=Mock(return_value=[])),
            result(None),
        ]
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=nullcontext(conn)),
        ):
            body = main.data_services("smoke", self.principal)
        self.assertEqual(body["services"], [])
        self.assertEqual(body["bindings"], [])

    def test_provider_error_is_visible_without_exposing_internal_details(self):
        conn = Mock()
        conn.execute.side_effect = [
            result((1,)),
            Mock(
                fetchall=Mock(
                    return_value=[
                        (
                            "resource-id",
                            "smoke",
                            "primary",
                            "postgresql",
                            "active",
                            "pending",
                            "ProviderUnavailable",
                        )
                    ]
                )
            ),
            Mock(fetchall=Mock(return_value=[])),
            result(None),
        ]
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=nullcontext(conn)),
        ):
            body = main.data_services("smoke", self.principal)
        self.assertEqual(body["services"][0]["state"], "unavailable")
        self.assertEqual(body["services"][0]["reason"], "ProviderUnavailable")

    def test_observation_failure_is_not_reported_as_a_missing_store(self):
        conn = Mock()
        conn.execute.side_effect = [
            result((1,)),
            RuntimeError("private database detail"),
        ]
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=nullcontext(conn)),
            self.assertRaises(HTTPException) as raised,
        ):
            main.data_services("smoke", self.principal)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("private", raised.exception.detail)

    def test_denied_view_cannot_query_named_resources(self):
        with (
            patch.object(
                main, "require_permission", side_effect=HTTPException(403, "Denied")
            ),
            patch.object(main, "connect") as connect,
            self.assertRaises(HTTPException) as raised,
        ):
            main.data_services("smoke", self.principal)
        self.assertEqual(raised.exception.status_code, 403)
        connect.assert_not_called()

    def test_creates_bounded_recovery_request(self):
        request_id = UUID(int=1)
        conn = Mock()
        conn.execute.side_effect = [
            result((1,)),
            result((request_id, "unavailable", "requested", self.timestamp, None)),
        ]
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "required_audit"),
            patch.object(main, "uuid4", return_value=request_id),
            patch.object(main, "connect", return_value=nullcontext(conn)),
        ):
            body = main.request_data_service_recovery(
                "smoke",
                main.DataServiceRecoveryRequest(reason="unavailable"),
                self.principal,
            )
        self.assertEqual(
            body,
            {
                "project": "smoke",
                "request_id": str(request_id),
                "reason": "unavailable",
                "status": "requested",
                "requested_at": self.timestamp.isoformat(),
                "reviewed_at": None,
            },
        )

    def test_operator_can_review_request(self):
        request_id = UUID(int=2)
        conn = Mock()
        conn.execute.return_value = result(
            (
                "smoke",
                request_id,
                "access",
                "acknowledged",
                self.timestamp,
                self.timestamp,
            )
        )
        with (
            patch.object(main, "require_platform_admin"),
            patch.object(main, "required_audit"),
            patch.object(main, "connect", return_value=nullcontext(conn)),
        ):
            body = main.review_data_service_recovery_request(
                request_id,
                main.DataServiceRecoveryReview(status="acknowledged"),
                self.principal,
            )
        self.assertEqual(body["status"], "acknowledged")
        self.assertEqual(body["project"], "smoke")

    def test_database_connection_failure_maps_to_a_safe_service_unavailable_response(
        self,
    ):
        response = asyncio.run(
            main.database_unavailable(
                Mock(), main.psycopg.OperationalError("sensitive detail")
            )
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.body, b'{"detail":"Platform database is temporarily unavailable"}'
        )


if __name__ == "__main__":
    unittest.main()
