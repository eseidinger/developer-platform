#!/usr/bin/env python3
"""Live check: project log reads, attribution, failure diagnosis and unauthenticated denial.

Usage: python3 scripts/log_drill.py   (run from the repository root on the lab host)
Requires the smoke project (smoke.py), the local API image and PLATFORM_ACCESS_TOKEN.
Adds one short-lived failing pod labelled as part of smoke and deletes it afterwards.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

token = os.environ.get("PLATFORM_ACCESS_TOKEN")
if not token:
    raise SystemExit("PLATFORM_ACCESS_TOKEN is required")
API = "http://127.0.0.1:8000"
kubectl = ["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig"]


def get(path, bearer=token):
    headers = {"Authorization": "Bearer " + bearer} if bearer else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


assert get("/projects/smoke/logs", None)[0] in (401, 403)
assert get("/projects/no-such-project/logs")[0] == 404
assert get("/projects/smoke/logs?tail=0")[0] == 422
print("unauthenticated read denied; unknown project 404; invalid limit 422")

status, body = get("/projects/smoke/logs?tail=20")
assert status == 200 and body["state"] == "ok" and body["lines"], (status, body)
assert len(body["lines"]) <= 20
for line in body["lines"]:
    assert line["pod"].startswith("smoke-") and line["container"] and line["timestamp"], line
assert [l["timestamp"] for l in body["lines"]] == sorted(l["timestamp"] for l in body["lines"])
print("smoke logs: %d line(s) from %s/%s" % (len(body["lines"]), body["lines"][0]["pod"], body["lines"][0]["container"]))

marker = "log-drill-%d" % int(time.time())
name = marker
code = "import sys; print('failure-marker password=hunter2 ' + sys.argv[1], flush=True); sys.exit(3)"
pod = {"apiVersion": "v1", "kind": "Pod",
    "metadata": {"name": name, "namespace": "project-smoke", "labels": {"app.kubernetes.io/name": "smoke"}},
    "spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
    "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
    "containers": [{"name": "failing", "image": "developer-platform-platform-api:latest",
        "imagePullPolicy": "Never", "command": ["python", "-c", code, marker],
        "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]}},
        "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}
subprocess.run(kubectl + ["apply", "-f", "-"], input=json.dumps(pod), text=True, check=True)
try:
    for attempt in range(60):
        phase = json.loads(subprocess.run(kubectl + ["-n", "project-smoke", "get", "pod", name, "-o", "json"],
            capture_output=True, text=True, check=True).stdout)["status"]["phase"]
        if phase == "Failed":
            break
        time.sleep(2)
    else:
        raise SystemExit("Failing pod did not terminate")
    status, body = get("/projects/smoke/logs?tail=200&since_seconds=600")
    assert status == 200, (status, body)
    found = [l for l in body["lines"] if l["pod"] == name]
    assert found and "failure-marker" in found[0]["message"] and marker in found[0]["message"], body["lines"][-5:]
    assert "hunter2" not in found[0]["message"], found[0]
    assert found[0]["container"] == "failing"
    print("failed instance diagnosed from its logs:", found[0]["message"])
finally:
    subprocess.run(kubectl + ["-n", "project-smoke", "delete", "pod", name, "--wait=false"], check=True)
print("PASS: logs attributed to pod/container, bounded and ordered, failure diagnosable, credential redacted, unauthenticated denied")
