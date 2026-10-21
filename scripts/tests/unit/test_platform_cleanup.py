"""Cleanup must preserve foreign projects and attempt every confirmed fixture."""

import unittest
from unittest.mock import Mock

from scripts.tests.support.platform_cleanup import Cleanup

PROJECT = "test-owned"
ID = "11111111-1111-1111-1111-111111111111"


def created(**values):
    return {"status": 201, "json": values}


class CleanupTests(unittest.TestCase):
    def cleaner(self, client):
        clock = iter(range(100))
        return Cleanup(
            client, seconds=3, sleep=lambda _: None, clock=lambda: next(clock)
        )

    def test_conflicting_project_is_never_retired_but_owned_partial_create_is(self):
        client = Mock()
        client.request.return_value = (200, {"status": "retired"})
        report = self.cleaner(client).run(
            {
                "project_creation": {
                    "results": [
                        created(name=PROJECT),
                        {"status": 409, "json": {"name": "foreign"}},
                    ]
                }
            }
        )
        client.request.assert_called_once_with(
            "GET", "/projects/test-owned/retirement-preview"
        )
        self.assertEqual(report["result"], "failed")
        self.assertIn("project_creation_unconfirmed", report["errors"])

    def test_lost_create_response_does_not_adopt_a_project(self):
        client = Mock()
        report = self.cleaner(client).run({"project_creation": {"status": -1}})
        client.request.assert_not_called()
        self.assertEqual(report["result"], "failed")

    def test_scope_change_fetches_fresh_preview_before_retry(self):
        client = Mock()
        client.request.side_effect = [
            (200, {"scope_token": "old"}),
            (409, {"code": "scope_changed"}),
            (200, {"scope_token": "new"}),
            (200, {"status": "retired"}),
        ]
        report = self.cleaner(client).run({"project_creation": created(name=PROJECT)})
        self.assertEqual(report["result"], "passed")
        self.assertEqual(client.request.call_args_list[3].args[2]["scope_token"], "new")

    def test_retirement_failure_still_revokes_persona_and_fails_report(self):
        client = Mock()
        client.request.side_effect = [(503, {}), (200, {"status": "revoked"})]
        report = self.cleaner(client).run(
            {
                "project_creation": created(name=PROJECT),
                "personas": created(credential_id=ID),
            }
        )
        self.assertEqual(report["result"], "failed")
        self.assertEqual(report["completed"], 1)
        client.request.assert_called_with("DELETE", "/platform/test-identities/" + ID)

    def test_pending_provider_cleanup_does_not_count_as_complete(self):
        client = Mock()
        client.request.return_value = (202, {"status": "revocation_pending"})
        report = self.cleaner(client).run({"personas": created(credential_id=ID)})
        self.assertEqual(report["result"], "failed")
        self.assertEqual(report["completed"], 0)

    def test_all_confirmed_personas_are_attempted_after_provider_failure(self):
        client = Mock()
        client.request.side_effect = [
            OSError("private response"),
            (200, {"status": "revoked"}),
        ]
        report = self.cleaner(client).run(
            {"personas": {"results": [created(credential_id=ID)] * 2}}
        )
        self.assertEqual(client.request.call_count, 2)
        self.assertEqual(report["result"], "failed")
        self.assertNotIn("private response", str(report))

    def test_malformed_persona_handle_does_not_prevent_later_cleanup(self):
        client = Mock()
        client.request.return_value = (200, {"status": "revoked"})
        report = self.cleaner(client).run(
            {
                "personas": {
                    "results": [
                        created(credential_id="not-a-uuid"),
                        created(credential_id=ID),
                    ]
                }
            }
        )
        self.assertEqual(client.request.call_count, 1)
        self.assertEqual(report["result"], "failed")

    def test_http_success_without_retired_state_is_not_successful_cleanup(self):
        client = Mock()
        client.request.side_effect = lambda method, path, *args: (
            (200, {"scope_token": "current"})
            if method == "GET"
            else (200, {"status": "retiring"})
        )
        report = self.cleaner(client).run({"project_creation": created(name=PROJECT)})
        self.assertEqual(report["result"], "failed")
        self.assertEqual(report["completed"], 0)

    def test_credentials_for_unowned_project_are_never_revoked(self):
        client = Mock()
        report = self.cleaner(client).run(
            {
                "credentials": [
                    {"project": "foreign", "creation": created(credential_id=ID)}
                ]
            }
        )
        client.request.assert_not_called()
        self.assertFalse(report["dataPurged"])


if __name__ == "__main__":
    unittest.main()
