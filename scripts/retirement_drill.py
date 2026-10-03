#!/usr/bin/env python3
"""Live check: preview, stale-token rejection, confirmed namespace removal and retained data.

Usage: python3 scripts/retirement_drill.py <project>   (run from the repository root on the lab host)
Pick a disposable project such as an earlier crashdrill<n>. It is retired by this check.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

token = os.environ.get("PLATFORM_ACCESS_TOKEN")
if not token or len(sys.argv) != 2:
    raise SystemExit("Usage: PLATFORM_ACCESS_TOKEN=... retirement_drill.py <project>")
name = sys.argv[1]
API = "http://127.0.0.1:8000"
kubectl = ["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig"]


def call(path, body=None):
    request = urllib.request.Request(API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def psql(database, query):
    result = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-U", "postgres",
        "-d", database, "-tAc", query], capture_output=True, text=True, check=True)
    return result.stdout.strip()


# The provisioner may delete project namespaces but nothing else (kube-system is protected by Kubernetes itself, so use platform-system) (server-side dry run, deletes nothing).
# The controller kubeconfig names the k3d container, which only resolves inside the Docker network.
host_server = subprocess.run(["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig", "config", "view", "--minify",
    "-o", "jsonpath={.clusters[0].cluster.server}"], capture_output=True, text=True, check=True).stdout
refused = subprocess.run(["kubectl", "--kubeconfig", ".runtime/controller.kubeconfig", "--server", host_server,
    "--tls-server-name", "kubernetes", "delete", "namespace", "platform-system", "--dry-run=server"],
    capture_output=True, text=True)
assert refused.returncode != 0 and "provisioner-namespace-delete" in refused.stderr, refused
print("controller denied deleting platform-system by admission policy")

status, preview = call("/projects/%s/retirement-preview" % name)
assert status == 200 and not preview["blockers"], (status, preview)
print("preview removes:", ", ".join(i["kind"] + "/" + i["name"] for i in preview["removes"]))
print("preview retains:", preview["retains"])
database = preview["retains"]["database"]
assert subprocess.run(kubectl + ["get", "namespace", "project-" + name], capture_output=True).returncode == 0

status, body = call("/projects/%s/retire" % name, {"confirm_name": name, "scope_token": "0" * 32})
assert status == 409 and body["code"] == "scope_changed", (status, body)
assert subprocess.run(kubectl + ["get", "namespace", "project-" + name], capture_output=True).returncode == 0
print("stale token rejected; namespace untouched")

for attempt in range(60):
    status, body = call("/projects/%s/retire" % name, {"confirm_name": name, "scope_token": preview["scope_token"]})
    print("retire ->", status, body.get("status"))
    if status == 200:
        break
    assert status == 202, (status, body)
    time.sleep(3)
else:
    raise SystemExit("Retirement did not complete")

assert subprocess.run(kubectl + ["get", "namespace", "project-" + name], capture_output=True).returncode != 0
assert psql("postgres", "SELECT count(*) FROM pg_database WHERE datname='%s'" % database) == "1"
assert psql("postgres", "SELECT count(*) FROM pg_roles WHERE rolname='%s'" % database) == "1"
inventory = psql("platform", "SELECT inventory FROM project_retirements r JOIN projects p USING (project_id) "
                 "WHERE p.name='%s'" % name)
assert database in inventory, inventory
assert psql("platform", "SELECT status FROM projects WHERE name='%s'" % name) == "retired"
print("inventory:", inventory)
print("PASS: preview, stale token rejected, namespace removed by the platform, database/role/inventory retained")
