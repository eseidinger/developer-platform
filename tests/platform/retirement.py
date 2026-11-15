"""Bounded cleanup for fixtures whose creation and ownership are confirmed."""

from .harness import DrillError, require, wait_for


def retire_project(api, project, seconds=180):
    operation = None

    def attempt():
        nonlocal operation
        try:
            if operation:
                result = api.request("GET", operation)
                require(result["state"] != "failed", "fixture_retirement_failed")
                return result["state"] == "succeeded"
            preview = api.request("GET", f"/v1/projects/{project}/retirement-preview")
            if preview.get("status") == "retired":
                return True
            if preview["blockers"]:
                return False
            result = api.request(
                "POST",
                f"/v1/projects/{project}/retire",
                {
                    "confirm_name": project,
                    "confirm_project_id": preview["project_id"],
                    "scope_token": preview["scope_token"],
                },
                statuses=(202, 409),
            )
            if result.get("code") == "scope_changed":
                return False
            operation = result["status_url"]
            return False
        except DrillError as error:
            if str(error) != "control_api_http_503":
                raise
            return False

    wait_for(attempt, "fixture_retirement", seconds)
