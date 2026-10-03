"""Live drill: secrets are write-only, reach the pods, rotate with a restart, and never leak. Run on the lab host."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("PLATFORM_URL", "http://127.0.0.1:8000")
TOKEN = os.environ["PLATFORM_ACCESS_TOKEN"]
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "smoke"
ADMIN = [os.environ.get("KUBECTL", "kubectl"), "--kubeconfig", ".runtime/admin.kubeconfig", "-n", "project-" + PROJECT]
MARK = "drill-" + uuid.uuid4().hex
SECOND = "rotated-" + uuid.uuid4().hex
NAME = "DRILL_SECRET"


def call(method, path, body=None, token=TOKEN):
    request = urllib.request.Request(BASE + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def kubectl(*args):
    return subprocess.run(ADMIN + list(args), capture_output=True, text=True)


def pod_uids():
    return sorted(kubectl("get", "pods", "-l", "app.kubernetes.io/name=" + PROJECT,
                          "-o", "jsonpath={.items[*].metadata.uid}").stdout.split())


def wait_active():
    deadline = time.time() + 150
    while time.time() < deadline:
        status, text = call("GET", f"/projects/{PROJECT}/secrets")
        assert status == 200, (status, text)
        state = json.loads(text)["activation"]["state"]
        if state == "active":
            return text
        print("  activation:", state)
        time.sleep(5)
    raise AssertionError("secret did not become active")


path = f"/projects/{PROJECT}/secrets"
seen = []
assert call("GET", path, token=None)[0] == 401
status, text = call("PUT", f"{path}/PGHOST", {"value": MARK})
assert status == 422, (status, text)
seen.append(text)
before = pod_uids()

status, text = call("PUT", f"{path}/{NAME}", {"value": MARK})
assert status == 202 and json.loads(text)["rollout_required"], (status, text)
seen.append(text)
seen.append(wait_active())
stored = kubectl("get", "secret", "app-secrets", "-o", "jsonpath={.data." + NAME + "}").stdout
import base64
assert base64.b64decode(stored).decode() == MARK, "value not stored in the project Secret"
after = pod_uids()
assert after and after != before, ("pods did not restart", before, after)
print("created -> value only in the project Secret, pods restarted and active")

env = kubectl("exec", "deploy/" + PROJECT, "--", "printenv", NAME)
if env.returncode == 0:
    assert env.stdout.strip() == MARK
    print("pod environment carries the value")
else:
    print("note: image has no printenv; pod env not inspected directly")

status, text = call("PUT", f"{path}/{NAME}", {"value": SECOND})
assert status == 202 and json.loads(text)["rotated"], (status, text)
seen.append(text)
seen.append(wait_active())
assert pod_uids() != after, "rotation did not restart the pods"
print("rotated -> pods restarted and active")

status, text = call("GET", path)
listing = json.loads(text)
assert [s["name"] for s in listing["secrets"]] == [NAME] and listing["secrets"][0]["changed_at"], listing
seen.append(text)
for extra in ("/revisions", "/configuration", "/drift"):
    seen.append(call("GET", f"/projects/{PROJECT}{extra}")[1])

status, text = call("DELETE", f"{path}/{NAME}")
assert status == 202, (status, text)
wait_active()
assert json.loads(call("GET", path)[1])["secrets"] == []
assert call("DELETE", f"{path}/{NAME}")[0] == 404

logs = subprocess.run(["docker", "compose", "logs", "--no-color", "platform-api"], capture_output=True, text=True).stdout
for value in (MARK, SECOND):
    assert not any(value in blob for blob in seen), "value appeared in an API response"
    assert value not in logs, "value appeared in the platform-api logs"
print("PASS: write-only, stored only in the project Secret, rotation restarts pods, no value in responses or logs")
