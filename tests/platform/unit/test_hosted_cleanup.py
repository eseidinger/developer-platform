"""Named-store retirement changes scope while owned fixture cleanup is polling."""

import unittest
from unittest.mock import Mock, patch

from tests.platform import harness


class HostedCleanupTests(unittest.TestCase):
    def test_retirement_refreshes_scope_after_named_store_state_changes(self):
        run = "0123456789ab"
        project = harness.project_names(run)["provider"]
        image = "example/fixture@sha256:" + "a" * 64
        journal = Mock()
        journal.state = {
            "runId": run,
            "projects": harness.project_names(run),
            "createdProjects": [project],
            "image": image,
            "personas": [],
            "clients": [],
            "human": None,
        }
        journal.report = {}
        scopes = []

        def request(method, path, body=None, **kwargs):
            if path == "/v1/projects":
                return [
                    {
                        "name": project,
                        "status": "applied",
                        "spec": {
                            "configuration": {"ACCEPTANCE_RUN_ID": run},
                            "components": [{"image": image}],
                        },
                    }
                ]
            if path.endswith("/retirement-preview"):
                return {
                    "project_id": "uuid",
                    "blockers": [],
                    "scope_token": "after" if scopes else "before",
                }
            if path.endswith("/retire"):
                self.assertEqual(method, "POST")
                expected = "after" if scopes else "before"
                self.assertEqual(
                    body,
                    {
                        "confirm_name": project,
                        "confirm_project_id": "uuid",
                        "scope_token": expected,
                    },
                )
                scopes.append(body["scope_token"])
                return (
                    {"code": "scope_changed"}
                    if len(scopes) == 1
                    else {
                        "state": "queued",
                        "status_url": "/v1/operations/retirement-op",
                    }
                )
            if path == "/v1/operations/retirement-op":
                return {"state": "succeeded"}
            self.assertTrue(path.startswith("/v1/platform/test-identities?"))
            return {"credentials": []}

        with patch.object(
            harness,
            "wait_for",
            side_effect=lambda ready, *args: self.assertTrue(ready() or ready()),
        ):
            harness.cleanup(journal, Mock(request=request), Mock())
        self.assertEqual(scopes, ["before", "after"])
        self.assertEqual(journal.report["cleanup"], "completed-data-retained")


if __name__ == "__main__":
    unittest.main()
