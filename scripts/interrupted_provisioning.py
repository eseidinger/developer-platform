#!/usr/bin/env python3
"""Live check: kill the API right after a project database is created, then repeat the request.

Run from the repository root on the lab host with a short-lived PLATFORM_ACCESS_TOKEN.
Needs `docker compose`, the local API image and the lab kubeconfig. Creates the project
`crashdrill` (retire it afterwards). It retries with a fresh project name until the kill
lands while the operation is still running.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

token = os.environ.get("PLATFORM_ACCESS_TOKEN")
if not token:
    raise SystemExit("Set a short-lived OIDC PLATFORM_ACCESS_TOKEN before running this check")
API = "http://127.0.0.1:8000"
kubectl = ["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig"]
compose = ["docker", "compose"]


def call(path, body=None):
    request = urllib.request.Request(API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method="PUT" if body is not None else "GET",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def psql(database, query):
    result = subprocess.run(compose + ["exec", "-T", "postgres", "psql", "-X", "-U", "postgres",
        "-d", database, "-tAc", query], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("psql failed: " + result.stderr.strip())
    return result.stdout.strip()


def wait_api():
    for attempt in range(60):
        try:
            call("/readyz")
            return
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    raise SystemExit("API did not come back")


def wait_ready(accepted):
    for attempt in range(150):
        operation = call(accepted["status_url"])
        if operation["state"] == "failed":
            raise SystemExit("Operation failed: " + accepted["operation_id"])
        if operation["state"] == "succeeded" and operation["readiness"]["state"] == "ready":
            return operation
        time.sleep(2)
    raise SystemExit("Not ready: " + accepted["operation_id"])


def operation_states(name):
    return psql("platform", """SELECT coalesce(string_agg(o.state || ':' || o.revision, ',' ORDER BY o.created_at), '')
        FROM projects p JOIN project_environments e ON e.project_id=p.project_id
        JOIN project_applications a ON a.environment_id=e.environment_id
        JOIN application_operations o ON o.application_id=a.application_id
        WHERE p.name='%s'""" % name)


def interrupted_attempt(name, spec):
    db = "project_" + name.replace("-", "_")
    accepted = call("/projects/" + name, spec)
    deadline = time.monotonic() + 60
    while psql("postgres", "SELECT 1 FROM pg_database WHERE datname='%s'" % db) != "1":
        if time.monotonic() > deadline:
            raise SystemExit("Database was never created for " + name)
    subprocess.run(compose + ["kill", "platform-api"], check=True)
    states = operation_states(name)
    return accepted, db, states


subprocess.run([".runtime/bin/k3d", "image", "import",
    "developer-platform-platform-api:latest", "-c", "workloads"], check=True)
for attempt in range(1, 6):
    name = "crashdrill" if attempt == 1 else "crashdrill%d" % attempt
    spec = {"name": name, "image": "hashicorp/http-echo:1.0.0", "port": 5678,
            "probe_profile": "hello-world"}
    accepted, db, states = interrupted_attempt(name, spec)
    print("attempt", attempt, name, "operations after kill:", states)
    if states.startswith("running"):
        break
    # The operation finished before the kill landed; restore the API and try a fresh project.
    subprocess.run(compose + ["up", "-d", "platform-api"], check=True)
    wait_api()
else:
    raise SystemExit("Could not interrupt an operation mid-flight in 5 attempts")

marker = "marker-" + str(int(time.time()))
psql(db, "CREATE TABLE crash_check (marker text); INSERT INTO crash_check VALUES ('%s')" % marker)
roles_before = psql("postgres", "SELECT count(*) FROM pg_roles WHERE rolname='%s'" % db)
print("database", db, "exists with marker", marker, "roles:", roles_before)

subprocess.run(compose + ["up", "-d", "platform-api"], check=True)
wait_api()
repeated = call("/projects/" + name, spec)
assert repeated["revision"] == accepted["revision"], (repeated, accepted)
wait_ready(repeated)

states = operation_states(name)
revisions = call("/projects/" + name + "/revisions")["revisions"]
assert len(revisions) == 1 and revisions[0]["revision"] == accepted["revision"], revisions
assert states.count(":") == 1 and states.startswith("succeeded"), states
assert psql("postgres", "SELECT count(*) FROM pg_database WHERE datname='%s'" % db) == "1"
assert psql("postgres", "SELECT count(*) FROM pg_roles WHERE rolname='%s'" % db) == "1"
assert psql(db, "SELECT marker FROM crash_check") == marker, "marker lost"
# The recreated workload must still authenticate with the same generated credentials.
code = ("import psycopg\nwith psycopg.connect(connect_timeout=5) as c:\n"
        "    print(c.execute('SELECT marker FROM crash_check').fetchone()[0])\n")
pod_name = "crash-read-" + str(int(time.time()))
pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": pod_name, "namespace": "project-" + name},
    "spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
    "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
    "containers": [{"name": "check", "image": "developer-platform-platform-api:latest",
        "imagePullPolicy": "Never", "command": ["python", "-c", code],
        "envFrom": [{"secretRef": {"name": "database"}}],
        "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]}},
        "resources": {"requests": {"cpu": "50m", "memory": "64Mi"},
                      "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}
subprocess.run(kubectl + ["apply", "-f", "-"], input=json.dumps(pod), text=True, check=True)
try:
    for attempt in range(90):
        info = json.loads(subprocess.run(kubectl + ["-n", "project-" + name, "get", "pod", pod_name, "-o", "json"],
                                         capture_output=True, text=True, check=True).stdout)
        phase = info["status"]["phase"]
        if phase in ("Succeeded", "Failed"):
            logs = subprocess.run(kubectl + ["-n", "project-" + name, "logs", pod_name],
                                  capture_output=True, text=True, check=True).stdout.strip()
            assert phase == "Succeeded" and logs == marker, (phase, logs)
            break
        time.sleep(2)
    else:
        raise SystemExit("Read pod timed out")
finally:
    subprocess.run(kubectl + ["-n", "project-" + name, "delete", "pod", pod_name, "--wait=false"], check=True)
print("PASS: interrupted after database creation; repeat request reused revision",
      accepted["revision"], "with one succeeded operation, one database and role, data and credentials intact")
