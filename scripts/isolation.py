#!/usr/bin/env python3
"""Live DB/NetworkPolicy checks; requires successful smoke.py and local API image."""
import json
import os
import subprocess
import time
import urllib.request
from env import settings

cfg = settings()
access_token = os.environ.get("PLATFORM_ACCESS_TOKEN")
if not access_token:
    raise SystemExit("Set a short-lived OIDC PLATFORM_ACCESS_TOKEN before running this check")
project = {"name": "isolation", "image": "hashicorp/http-echo:1.0.0", "port": 5678}
req = urllib.request.Request("http://127.0.0.1:8000/projects/isolation",
    data=json.dumps(project).encode(), method="PUT",
    headers={"Authorization": "Bearer " + access_token, "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as response:
    assert response.status == 200
kubectl = ["kubectl", "--kubeconfig", ".runtime/admin.kubeconfig"]
subprocess.run(kubectl + ["-n", "project-isolation", "rollout", "status",
    "deployment/isolation", "--timeout=180s"], check=True)
subprocess.run([".runtime/bin/k3d", "image", "import",
    "developer-platform-platform-api:latest", "-c", "workloads"], check=True)
code = """
import os, socket, psycopg, time
# kube-router reconciles policy membership asynchronously for new pods.
time.sleep(15)
with psycopg.connect(connect_timeout=5) as conn:
    assert conn.execute('SELECT current_database()').fetchone()[0] == 'project_smoke'
for database in ('project_isolation', 'platform'):
    try:
        psycopg.connect(dbname=database, connect_timeout=5)
    except psycopg.OperationalError:
        pass
    else:
        raise AssertionError('Cross-project database access was allowed')
# DNS is permitted; TCP to another project and internet must be blocked.
socket.getaddrinfo('isolation.project-isolation.svc.cluster.local', 80)
for host, port in [('isolation.project-isolation.svc.cluster.local', 80), ('1.1.1.1', 443)]:
    try:
        socket.create_connection((host, port), timeout=4)
    except (socket.timeout, ConnectionRefusedError, OSError):
        pass
    else:
        raise AssertionError('Unexpected egress to ' + host)
print('PASS: own PostgreSQL, denied foreign DB/platform DB, DNS, namespace and internet isolation')
"""
name = "isolation-check-" + str(int(time.time()))
pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {
    "name": name, "namespace": "project-smoke"}, "spec": {
    "restartPolicy": "Never", "automountServiceAccountToken": False,
    "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
        "seccompProfile": {"type": "RuntimeDefault"}},
    "containers": [{"name": "check", "image": "developer-platform-platform-api:latest",
        "imagePullPolicy": "Never", "command": ["python", "-c", code],
        "envFrom": [{"secretRef": {"name": "database"}}],
        "securityContext": {"allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
        "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                      "limits": {"cpu": "500m", "memory": "256Mi"}}}]}}
subprocess.run(kubectl + ["apply", "-f", "-"], input=json.dumps(pod), text=True, check=True)
try:
    for attempt in range(90):
        result = subprocess.run(kubectl + ["-n", "project-smoke", "get", "pod", name, "-o", "json"],
                                capture_output=True, text=True, check=True)
        phase = json.loads(result.stdout)["status"]["phase"]
        if phase in ("Succeeded", "Failed"):
            subprocess.run(kubectl + ["-n", "project-smoke", "logs", name], check=True)
            if phase != "Succeeded":
                raise SystemExit("Isolation test failed")
            break
        time.sleep(2)
    else:
        raise SystemExit("Isolation test timed out")
finally:
    subprocess.run(kubectl + ["-n", "project-smoke", "delete", "pod", name, "--wait=false"], check=True)
