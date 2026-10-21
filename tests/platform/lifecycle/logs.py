"""Failed-pod attribution and credential redaction with an already deployed image."""

import json
from uuid import uuid4

from ..harness import require, wait_for


def check_logs(fixture):
    fixture.request("GET", "/logs?tail=0", statuses=(422,))
    marker = "lifecycle-log-" + uuid4().hex[:12]
    code = (
        "import sys; print('failure-marker password=hunter2 ' + sys.argv[1]); "
        "print('second-line ' + sys.argv[1], flush=True); sys.exit(3)"
    )
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": marker,
            "namespace": "project-" + fixture.project,
            "labels": {"app.kubernetes.io/name": fixture.project},
        },
        "spec": {
            "restartPolicy": "Never",
            "automountServiceAccountToken": False,
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 10001,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [
                {
                    "name": "failing",
                    "image": fixture.args.fixture_image,
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["python", "-c", code, marker],
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                    "resources": {
                        "requests": {"cpu": "50m", "memory": "64Mi"},
                        "limits": {"cpu": "250m", "memory": "128Mi"},
                    },
                }
            ],
        },
    }
    try:
        fixture.kubectl("apply", "-f", "-", input=json.dumps(pod))
        wait_for(
            lambda: (
                json.loads(fixture.kubectl("get", "pod", marker, "-o", "json").stdout)[
                    "status"
                ]["phase"]
                == "Failed"
            ),
            "failed_pod_timeout",
        )
        body = fixture.request("GET", "/logs?tail=200&since_seconds=600")
        lines = [line for line in body["lines"] if line["pod"] == marker]
        require(body["state"] == "ok" and len(lines) == 2, "failed_pod_logs_missing")
        require(
            "failure-marker" in lines[0]["message"]
            and marker in lines[0]["message"]
            and "hunter2" not in lines[0]["message"],
            "log_redaction_failed",
        )
        require(
            lines[1]["message"] == "second-line " + marker, "log_line_framing_failed"
        )
        require(
            all(
                line["container"] == "failing"
                and line["timestamp"].endswith("Z")
                and "\\n" not in line["message"]
                for line in lines
            ),
            "log_attribution_failed",
        )
        require(
            [line["timestamp"] for line in lines]
            == sorted(line["timestamp"] for line in lines),
            "log_order_failed",
        )
        fixture.check("failed-pod-log-attribution-order-and-redaction")
    finally:
        fixture.kubectl("delete", "pod", marker, "--ignore-not-found", "--wait=false")
