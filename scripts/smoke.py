#!/usr/bin/env python3
"""Exercise the local stack. Creates/updates the explicitly named smoke project."""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from env import settings

cfg = settings()
access_token = os.environ.get("PLATFORM_ACCESS_TOKEN")
if not access_token:
    raise SystemExit("Set a short-lived OIDC PLATFORM_ACCESS_TOKEN before running this check")
def request(path, body=None, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + access_token
    req = urllib.request.Request("http://127.0.0.1:8000" + path,
        data=json.dumps(body).encode() if body else None,
        method="PUT" if body else "GET", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

for attempt in range(60):
    try:
        request("/readyz")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("API dependencies not ready")

try:
    request("/projects", token=False)
    raise AssertionError("Unauthenticated project access succeeded")
except urllib.error.HTTPError as error:
    assert error.code in (401, 403)

project = {"name": "smoke", "image": "hashicorp/http-echo:1.0.0", "port": 5678, "probe_profile": "hello-world"}
assert request("/projects/smoke", project)["status"] == "applied"
assert request("/projects/smoke", project)["status"] == "applied"
assert sum(p["name"] == "smoke" for p in request("/projects")) == 1
subprocess.run(["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig",
    "-n", "project-smoke", "rollout", "status", "deployment/smoke", "--timeout=180s"], check=True)
req = urllib.request.Request("http://127.0.0.1/", headers={"Host": "smoke." + cfg["APPS_DOMAIN"]})
for attempt in range(30):
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            assert response.status == 200
        break
    except urllib.error.HTTPError as error:
        if error.code not in (404, 502, 503, 504):
            raise
        time.sleep(2)
else:
    raise SystemExit("Ingress did not converge")
print("PASS: authentication, readiness, idempotent provisioning, rollout and edge routing")
