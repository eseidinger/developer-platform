"""Bounded cleanup for fixtures whose creation and ownership are confirmed."""

from .harness import DrillError, require, wait_for


def retire_project(api, project, seconds=180):
    def attempt():
        try:
            preview = api.request("GET", f"/projects/{project}/retirement-preview")
            if preview.get("status") == "retired":
                return True
            if preview["blockers"]:
                return False
            # Provider revocation changes the scope while namespace deletion
            # progresses. Never reuse a token from an earlier polling attempt.
            result = api.request(
                "POST",
                f"/projects/{project}/retire",
                {"confirm_name": project, "scope_token": preview["scope_token"]},
                statuses=(200, 202, 409),
            )
            if result.get("code") == "scope_changed":
                return False
            require(
                result.get("status") in {"retired", "retiring"},
                "unexpected_retirement_response",
            )
            return result["status"] == "retired"
        except DrillError as error:
            if str(error) != "control_api_http_503":
                raise
            return False

    wait_for(attempt, "fixture_retirement", seconds)
