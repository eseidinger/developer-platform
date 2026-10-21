"""Live drill: configuration is validated, versioned, rolled out and observable. Run on the lab host."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PLATFORM_URL", "http://127.0.0.1:8000")
TOKEN = os.environ["PLATFORM_ACCESS_TOKEN"]
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "smoke"


def call(method, path, body=None, headers=None, token=TOKEN):
    request = urllib.request.Request(BASE + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {}),
                                              **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def wait_active(expected):
    deadline = time.time() + 150
    while time.time() < deadline:
        status, body = call("GET", f"/projects/{PROJECT}/configuration")
        assert status == 200, (status, body)
        if body["values"] == expected and body["activation"]["state"] == "active":
            return body
        print("  activation:", body["activation"]["state"])
        time.sleep(5)
    raise AssertionError("configuration did not become active")


path = f"/projects/{PROJECT}/configuration"
assert call("GET", path, token=None)[0] == 401
for bad in ({"PGHOST": "x"}, {"DB_PASSWORD": "x"}, {"A": "x" * 2000}):
    status, body = call("PUT", path, {"values": bad})
    assert (status, body["code"]) == (422, "invalid_configuration"), (bad, status, body)
print("invalid, reserved and secret-like configuration rejected before any change")

start = call("GET", path)[1]
status, body = call("PUT", path, {"values": {"DRILL_MODE": "one"}}, {"If-Match": str(start["revision"] + 5)})
assert status == 409, (status, body)
status, body = call("PUT", path, {"values": {"DRILL_MODE": "one", "DRILL_FLAG": "on"}},
                    {"If-Match": str(start["revision"])})
assert status == 202 and body["rollout_required"], (status, body)
first = wait_active({"DRILL_MODE": "one", "DRILL_FLAG": "on"})
print("added -> active at revision", first["revision"])

status, body = call("PUT", path, {"values": {"DRILL_MODE": "two"}})
assert status == 202, (status, body)
second = wait_active({"DRILL_MODE": "two"})
assert second["revision"] > first["revision"]
print("updated and removed -> active at revision", second["revision"])

status, body = call("PUT", path, {"values": {}})
assert status == 202, (status, body)
final = wait_active({})
drift = call("GET", f"/projects/{PROJECT}/drift")[1]
assert drift["state"] == "in_sync", drift
print("PASS: validated, versioned, rolled out, activation observed, no drift; final revision", final["revision"])
