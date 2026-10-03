#!/usr/bin/env python3
"""Live check: data written to the managed database survives a spec redeploy and a restart.

Requires the smoke project (smoke.py) and the local API image. Leaves one row per run in
the smoke database table platform_data_check.
"""
import json
import os
import subprocess
import time
import urllib.request

token = os.environ.get("PLATFORM_ACCESS_TOKEN")
if not token:
    raise SystemExit("Set a short-lived OIDC PLATFORM_ACCESS_TOKEN before running this check")
API = "http://127.0.0.1:8000"
kubectl = ["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig"]


def call(path, body=None, method=None):
    request = urllib.request.Request(API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method or ("PUT" if body is not None else "GET"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def wait_ready(accepted):
    for attempt in range(150):
        operation = call(accepted["status_url"])
        if operation["state"] == "failed":
            raise SystemExit("Operation failed: " + accepted["operation_id"])
        if operation["state"] == "succeeded" and operation["readiness"]["state"] == "ready":
            return
        time.sleep(2)
    raise SystemExit("Not ready: " + accepted["operation_id"])


def run_sql(action, marker):
    code = """
import psycopg, sys
action, marker = sys.argv[1:3]
with psycopg.connect(connect_timeout=5) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS platform_data_check (marker text PRIMARY KEY, written timestamptz DEFAULT now())')
    if action == 'write':
        conn.execute('INSERT INTO platform_data_check (marker) VALUES (%s)', (marker,))
        print('WROTE', marker)
    else:
        row = conn.execute('SELECT marker FROM platform_data_check WHERE marker = %s', (marker,)).fetchone()
        assert row is not None, 'row ' + marker + ' is missing'
        print('READ', row[0])
"""
    name = "data-check-" + action + "-" + str(int(time.time()))
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": "project-smoke"},
        "spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
            "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [{"name": "check", "image": "developer-platform-platform-api:latest",
            "imagePullPolicy": "Never", "command": ["python", "-c", code, action, marker],
            "envFrom": [{"secretRef": {"name": "database"}}],
            "securityContext": {"allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
            "resources": {"requests": {"cpu": "50m", "memory": "64Mi"},
                          "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}
    subprocess.run(kubectl + ["apply", "-f", "-"], input=json.dumps(pod), text=True, check=True)
    try:
        for attempt in range(90):
            result = subprocess.run(kubectl + ["-n", "project-smoke", "get", "pod", name, "-o", "json"],
                                    capture_output=True, text=True, check=True)
            phase = json.loads(result.stdout)["status"]["phase"]
            if phase in ("Succeeded", "Failed"):
                subprocess.run(kubectl + ["-n", "project-smoke", "logs", name], check=True)
                if phase != "Succeeded":
                    raise SystemExit("Database " + action + " failed")
                return
            time.sleep(2)
        raise SystemExit("Database " + action + " timed out")
    finally:
        subprocess.run(kubectl + ["-n", "project-smoke", "delete", "pod", name, "--wait=false"], check=True)


subprocess.run([".runtime/bin/k3d", "image", "import",
    "developer-platform-platform-api:latest", "-c", "workloads"], check=True)
marker = "marker-" + str(int(time.time()))
run_sql("write", marker)

before = call("/projects/smoke/revisions")["current_revision"]
# A new revision with a distinct CPU limit forces a real redeploy of the Deployment.
smoke = {"name": "smoke", "image": "hashicorp/http-echo:1.0.0", "port": 5678,
         "probe_profile": "hello-world",
         "resources": {"limits": {"cpu": str(500 + int(time.time()) % 400) + "m"}}}
accepted = call("/projects/smoke", smoke)
assert accepted["revision"] > before, accepted
wait_ready(accepted)
run_sql("read", marker)

wait_ready(call("/projects/smoke/restart", {}, "POST"))
run_sql("read", marker)
print("PASS: database row written before redeploy survived a new revision and a restart")
