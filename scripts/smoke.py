#!/usr/bin/env python3
"""Exercise the local stack. Creates/updates the explicitly named smoke project."""
import http.client
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from time import monotonic
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

def wait_for_operation(accepted, timeout=300):
    deadline = monotonic() + timeout
    last = "no status observed"
    while monotonic() < deadline:
        operation = request(accepted["status_url"])
        if operation["state"] == "failed":
            raise RuntimeError("Deployment failed; operation " + accepted["operation_id"])
        readiness = operation["readiness"]
        last = "operation=" + operation["state"] + " readiness=" + readiness["state"] + " reason=" + str(readiness["reason"])
        print("operation", accepted["operation_id"], operation["state"], "readiness", readiness["state"], flush=True)
        if operation["state"] == "succeeded":
            if readiness["state"] == "ready":
                return operation
            if readiness["state"] == "failed":
                raise RuntimeError("Deployment rollout failed; operation "
                                   + accepted["operation_id"] + " reason="
                                   + str(readiness["reason"]))
        time.sleep(2)
    raise TimeoutError("Application readiness observation timed out: "
                       + accepted["operation_id"] + " last " + last)

for attempt in range(60):
    try:
        request("/readyz")
        break
    except Exception as error:
        print("waiting for API on 127.0.0.1:8000:", error, flush=True)
        time.sleep(2)
else:
    raise SystemExit("API dependencies not ready; run this on the lab host or tunnel ports 8000 and 80")

try:
    request("/projects", token=False)
    raise AssertionError("Unauthenticated project access succeeded")
except urllib.error.HTTPError as error:
    assert error.code in (401, 403)

project = {"name": "smoke", "image": "hashicorp/http-echo:1.0.0", "port": 5678, "probe_profile": "hello-world"}
first = request("/projects/smoke", project)
second = request("/projects/smoke", project)
assert first["operation_id"] == second["operation_id"]
wait_for_operation(second)
assert sum(p["name"] == "smoke" for p in request("/projects")) == 1
host = "smoke." + cfg["APPS_DOMAIN"]


def edge_status():
    # Connect to the local proxy but verify and route by the public hostname.
    connection = http.client.HTTPSConnection(host, 443, timeout=10)
    connection.sock = ssl.create_default_context().wrap_socket(
        socket.create_connection(("127.0.0.1", 443), timeout=10), server_hostname=host
    )
    try:
        connection.request("GET", "/", headers={"Host": host})
        return connection.getresponse().status
    finally:
        connection.close()


for attempt in range(30):
    try:
        status = edge_status()
    except (OSError, ssl.SSLError):
        status = None
    if status == 200:
        break
    time.sleep(2)
else:
    raise SystemExit("Ingress did not converge")
print("PASS: authentication, readiness, idempotent provisioning, rollout and edge routing")
