"""Fixture cleanup refreshes changing provider scopes and remains bounded."""

import unittest
from unittest.mock import Mock, patch

from tests.platform import retirement
from tests.platform.harness import DrillError, wait_for


class RetirementTests(unittest.TestCase):
    def retire(self, api, seconds=100):
        clock = iter(range(1000))
        with patch.object(
            retirement,
            "wait_for",
            side_effect=lambda action, code, limit: wait_for(
                action, code, limit, clock=lambda: next(clock), sleep=lambda _: None
            ),
        ):
            retirement.retire_project(api, "owned-fixture", seconds)

    def test_scope_conflict_refreshes_preview_then_polls_one_durable_operation(self):
        api = Mock()
        api.request.side_effect = [
            {
                "status": "applied",
                "project_id": "uuid",
                "blockers": [],
                "scope_token": "first",
            },
            {"code": "scope_changed"},
            {
                "status": "applied",
                "project_id": "uuid",
                "blockers": [],
                "scope_token": "second",
            },
            {"state": "queued", "status_url": "/v1/operations/retire"},
            {"state": "running"},
            {"state": "succeeded"},
        ]
        self.retire(api)
        tokens = [
            call.args[2]["scope_token"]
            for call in api.request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(tokens, ["first", "second"])
        self.assertEqual(
            api.request.call_args_list[-1].args, ("GET", "/v1/operations/retire")
        )

    def test_transient_provider_failure_retries_but_authorization_failure_propagates(
        self,
    ):
        api = Mock()
        api.request.side_effect = [
            DrillError("control_api_http_503"),
            {"status": "retired"},
        ]
        self.retire(api)
        api.request.side_effect = DrillError("control_api_http_403")
        with self.assertRaisesRegex(DrillError, "control_api_http_403"):
            self.retire(api)

    def test_active_blockers_are_polled_before_a_retirement_mutation(self):
        api = Mock()
        api.request.side_effect = [
            {"blockers": ["active-operation"]},
            {"blockers": [], "project_id": "uuid", "scope_token": "ready"},
            {"state": "queued", "status_url": "/v1/operations/retire"},
            {"state": "succeeded"},
        ]
        self.retire(api)
        self.assertEqual(
            [call.args[0] for call in api.request.call_args_list],
            ["GET", "GET", "POST", "GET"],
        )

    def test_persistent_blocker_expires_without_retiring_or_purging_anything(self):
        api = Mock()
        api.request.return_value = {"blockers": ["active-operation"]}
        with self.assertRaisesRegex(DrillError, "fixture_retirement"):
            self.retire(api, seconds=3)
        self.assertTrue(
            all(call.args[0] == "GET" for call in api.request.call_args_list)
        )
