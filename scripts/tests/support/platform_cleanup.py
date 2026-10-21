"""Clean confirmed Ansible test fixtures; consume credentials only through stdin.

This helper never adopts projects by name or purges retained data. Its JSON
output contains fixed error codes and counts, never dependency response bodies.
"""

import json
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID


class CleanupError(Exception):
    """A non-secret, fixed cleanup failure code."""


def responses(value):
    if isinstance(value, dict):
        return value.get("results", [value]) if value else []
    return value


def confirmed(value):
    return [
        row["json"]
        for row in responses(value)
        if row.get("status") == 201 and isinstance(row.get("json"), dict)
    ]


class Client:
    def __init__(self, configuration):
        self.configuration = configuration
        self.token = None
        self.refresh_at = 0

    def request(self, method, path, body=None):
        if time.monotonic() >= self.refresh_at:
            data = urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.configuration["client_id"],
                    "client_secret": self.configuration["client_secret"],
                }
            ).encode()
            request = Request(self.configuration["token_url"], data=data, method="POST")
            with urlopen(request, timeout=20) as response:
                token = json.load(response)
            self.token = token["access_token"]
            self.refresh_at = time.monotonic() + max(1, int(token["expires_in"]) - 30)
        request = Request(
            self.configuration["api"].rstrip("/") + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read() or b"{}")
        except HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")


class Cleanup:
    def __init__(self, client, *, seconds=240, sleep=time.sleep, clock=time.monotonic):
        self.client, self.seconds, self.sleep, self.clock = (
            client,
            seconds,
            sleep,
            clock,
        )
        self.errors = []
        self.completed = 0

    def poll(self, action):
        deadline = self.clock() + self.seconds
        while not action():
            if self.clock() >= deadline:
                raise CleanupError("cleanup_timeout")
            self.sleep(2)

    def attempt(self, action):
        try:
            self.poll(action)
            self.completed += 1
        except (CleanupError, OSError, ValueError, KeyError):
            # Continue through all owned fixtures; no raw error or response body
            # can escape into Ansible output or prevent later cleanup attempts.
            self.errors.append("fixture_cleanup_incomplete")

    def revoke(self, path):
        status, body = self.client.request("DELETE", path)
        if status == 404:
            return True
        if status not in (200, 202):
            raise CleanupError("revocation_failed")
        return status == 200 and body.get("status") == "revoked"

    def retire(self, project):
        path = "/projects/" + project
        status, preview = self.client.request("GET", path + "/retirement-preview")
        if status == 404 or (status == 200 and preview.get("status") == "retired"):
            return True
        if status != 200:
            raise CleanupError("preview_failed")
        if preview.get("blockers"):
            return False
        status, result = self.client.request(
            "POST",
            path + "/retire",
            {"confirm_name": project, "scope_token": preview["scope_token"]},
        )
        if status == 409 and result.get("code") == "scope_changed":
            return False  # Next attempt obtains the current scope, not a stale token.
        if status not in (200, 202, 404):
            raise CleanupError("retirement_failed")
        return status == 404 or (status == 200 and result.get("status") == "retired")

    def run(self, payload):
        creations = responses(payload.get("project_creation", {}))
        if any(row.get("status") != 201 for row in creations):
            self.errors.append("project_creation_unconfirmed")
        projects = []
        for row in confirmed(payload.get("project_creation", {})):
            project = row.get("name", "")
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", project):
                self.errors.append("invalid_project_name")
                continue
            projects.append(project)
        for credential in payload.get("credentials", []):
            if credential["project"] not in projects:
                continue
            for row in confirmed(credential["creation"]):
                self.attempt(
                    lambda p=credential["project"], r=row: self.revoke(
                        "/projects/"
                        + p
                        + "/deployment-credentials/"
                        + str(UUID(r["credential_id"]))
                    )
                )
        for project in projects:
            self.attempt(lambda p=project: self.retire(p))
        for row in confirmed(payload.get("personas", {})):
            self.attempt(
                lambda r=row: self.revoke(
                    "/platform/test-identities/" + str(UUID(r["credential_id"]))
                )
            )
        return {
            "completed": self.completed,
            "errors": self.errors,
            "result": "failed" if self.errors else "passed",
            "dataPurged": False,
        }


def main():
    try:
        payload = json.load(sys.stdin)
        report = Cleanup(Client(payload)).run(payload)
    except (OSError, ValueError, KeyError, CleanupError):
        report = {
            "result": "failed",
            "errors": ["invalid_cleanup_input"],
            "dataPurged": False,
        }
    print(json.dumps(report))
    return int(report["result"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
