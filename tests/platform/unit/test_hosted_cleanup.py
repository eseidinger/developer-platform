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
            if path == "/projects":
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
                return {"blockers": [], "scope_token": "after" if scopes else "before"}
            if path.endswith("/retire"):
                self.assertEqual(method, "POST")
                expected = "after" if scopes else "before"
                self.assertEqual(
                    body, {"confirm_name": project, "scope_token": expected}
                )
                scopes.append(body["scope_token"])
                return {"status": "retired" if len(scopes) == 2 else "retiring"}
            self.assertTrue(path.startswith("/platform/test-identities?"))
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
