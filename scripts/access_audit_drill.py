"""Live drill: a user without grants is denied every Phase 1C project endpoint, and the audit export
records the owner's actions by name without values. Run on the lab host.

Needs PLATFORM_ACCESS_TOKEN (project owner), OTHER_TOKEN (a user with no grant on the project) and
optionally PLATFORM_ADMIN_TOKEN (operator, for the audit export). Tokens come from the environment only.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("PLATFORM_URL", "http://127.0.0.1:8000")
OWNER = os.environ["PLATFORM_ACCESS_TOKEN"]
OTHER = os.environ.get("OTHER_TOKEN")
ADMIN = os.environ.get("PLATFORM_ADMIN_TOKEN")
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "smoke"
MARK = "audit-" + uuid.uuid4().hex
NAME = "AUDIT_DRILL"


def call(method, path, token, body=None):
    request = urllib.request.Request(BASE + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


p = f"/projects/{PROJECT}"
calls = [("GET", p + "/configuration", None), ("PUT", p + "/configuration", {"values": {"X_DENIED": "1"}}),
         ("GET", p + "/secrets", None), ("PUT", f"{p}/secrets/{NAME}", {"value": MARK}),
         ("POST", f"{p}/secrets/{NAME}/confirm", None), ("POST", f"{p}/secrets/{NAME}/revert", None),
         ("DELETE", f"{p}/secrets/{NAME}", None), ("GET", p + "/logs", None),
         ("GET", p + "/resource-usage", None), ("GET", p + "/revisions", None),
         ("GET", p + "/retirement-preview", None), ("POST", p + "/restart", None)]

start = datetime.now(timezone.utc) - timedelta(seconds=5)
before = json.loads(call("GET", p + "/secrets", OWNER)[1])["secrets"]
if OTHER:
    for method, path, body in calls:
        status, text = call(method, path, OTHER, body)
        assert status in (403, 404), (method, path, status)
        assert MARK not in text
    assert call("GET", p + "/secrets", None)[0] == 401
    after = json.loads(call("GET", p + "/secrets", OWNER)[1])["secrets"]
    assert after == before, "a denied request changed the secrets"
    print(f"user without grants denied on {len(calls)} endpoints; nothing changed")
else:
    print("skipped: OTHER_TOKEN not set, cross-project denial not exercised")

assert call("PUT", f"{p}/secrets/{NAME}", OWNER, {"value": MARK})[0] == 202
assert call("DELETE", f"{p}/secrets/{NAME}", OWNER)[0] == 202
call("GET", p + "/configuration", OWNER)
call("GET", p + "/logs", OWNER)
call("GET", p + "/resource-usage", OWNER)

if ADMIN:
    query = urllib.parse.urlencode({"start": start.isoformat(), "end": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
                                    "limit": 2000})
    status, text = call("GET", "/operator/audit/events?" + query, ADMIN)
    assert status == 200, status
    assert MARK not in text, "secret value appeared in the audit export"
    events = json.loads(text)["events"]
    seen = {(e["action"], e["result"]) for e in events if e.get("target_id") == PROJECT}
    for action in ("project.secret.set", "project.secret.delete", "project.configuration.read",
                   "project.logs.read", "project.usage.inspect"):
        assert (action, "succeeded") in seen, ("missing audit record", action)
    names = [e for e in events if e["action"] == "project.secret.set" and e.get("target_id") == PROJECT]
    assert any(NAME in json.dumps(e["detail"]) for e in names), "secret name not recorded"
    print(f"audit export holds {len(events)} events; secret and read actions recorded by name, no value")
else:
    print("skipped: PLATFORM_ADMIN_TOKEN not set, audit export not checked")
print("PASS")
