#!/usr/bin/env python3
"""Non-mutating Phase 1B operator-inspection and audit-export smoke check.

Set PLATFORM_ADMIN_TOKEN and PHASE1B_PROJECT in a trusted shell. Optionally set
DEVELOPER_TOKEN to prove that a non-operator cannot read the operator surfaces.
No token, response body, actor identifier, or audit detail is printed.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = os.environ.get("PLATFORM_API", "http://127.0.0.1:8000")
SENSITIVE = ("password", "secret", "token", "authorization", "credential", "cookie", "key")
REDACTED = "[REDACTED]"


def request(path, token):
    try:
        with urlopen(Request(API + path, headers={"Authorization": "Bearer " + token}), timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def assert_redacted(value, key=""):
    if any(word in key.lower() for word in SENSITIVE):
        assert value == REDACTED, "sensitive audit field was not redacted"
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            assert_redacted(child_value, str(child_key))
    elif isinstance(value, list):
        for child_value in value:
            assert_redacted(child_value)
    elif isinstance(value, str):
        assert "bearer " not in value.lower(), "bearer value appeared in audit export"


def main():
    admin_token = os.environ.get("PLATFORM_ADMIN_TOKEN")
    project = os.environ.get("PHASE1B_PROJECT")
    if not admin_token or not project:
        raise SystemExit("Set PLATFORM_ADMIN_TOKEN and PHASE1B_PROJECT; do not pass tokens as command arguments.")
    start = datetime.now(timezone.utc) - timedelta(minutes=20)
    end = datetime.now(timezone.utc)
    checks = [
        ("permissions", f"/operator/projects/{project}/permissions"),
        ("security configuration", f"/operator/projects/{project}/security-configuration"),
        ("audit export", "/operator/audit/events?" + urlencode({
            "start": start.isoformat(), "end": end.isoformat(), "limit": 1000,
        })),
    ]
    for label, path in checks:
        status, body = request(path, admin_token)
        assert status == 200, f"{label} returned HTTP {status}"
        payload = json.loads(body)
        if label == "security configuration":
            workload = payload["workload_security"]
            assert workload["service_account_token_automount"] is False
            assert workload["container"]["allowPrivilegeEscalation"] is False
            assert workload["container"]["readOnlyRootFilesystem"] is True
        if label == "audit export":
            assert_redacted(payload["events"])
        print(f"PASS {label}")
    developer_token = os.environ.get("DEVELOPER_TOKEN")
    if developer_token:
        for label, path in checks:
            status, _ = request(path, developer_token)
            assert status == 403, f"developer {label} returned HTTP {status}, expected 403"
        print("PASS developer operator-surface denial")
    else:
        print("SKIP developer operator-surface denial (DEVELOPER_TOKEN is unset)")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
