"""Presentation names never change hosted-access resource identity or versions."""

import copy
import unittest
from unittest.mock import Mock, patch

from app import access_store


class PrincipalNameTests(unittest.TestCase):
    def test_names_are_batched_and_missing_names_keep_the_principal_id(self):
        rows = [
            {"version": 3, "spec": {"principalId": "known"}},
            {"version": 7, "spec": {"principalId": "unknown"}},
        ]
        original = copy.deepcopy(rows)
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [("known", "alice")]

        result = access_store.with_principal_names(conn, rows)

        self.assertEqual(result[0]["spec"]["displayName"], "alice")
        self.assertIsNone(result[1]["spec"]["displayName"])
        self.assertEqual(result[1]["spec"]["principalId"], "unknown")
        self.assertEqual([row["version"] for row in result], [3, 7])
        self.assertEqual(rows, original)
        conn.execute.assert_called_once()
        query, parameters = conn.execute.call_args.args
        self.assertIn("p.issuer=h.issuer AND p.subject=h.subject", query)
        self.assertEqual(set(parameters[0]), {"known", "unknown"})

    def test_empty_listing_does_not_query_identities(self):
        conn = Mock()
        self.assertEqual(access_store.with_principal_names(conn, []), [])
        conn.execute.assert_not_called()

    def test_enrollment_updates_names_without_changing_existing_requests(self):
        conn = Mock()
        request = {"state": "approved", "version": 4}
        with (
            patch.object(access_store, "principal", return_value="prn_alice"),
            patch.object(access_store, "by_name", return_value=request),
        ):
            result = access_store.enroll(
                conn, {"id": "policy", "project": "app"}, "issuer", "alice-id", "Alice"
            )
            self.assertEqual(result, ("prn_alice", request))
            self.assertEqual(
                conn.execute.call_args.args[1], ("Alice", "issuer", "alice-id")
            )
            conn.reset_mock()
            access_store.enroll(
                conn, {"id": "policy", "project": "app"}, "issuer", "alice-id"
            )
            conn.execute.assert_not_called()
