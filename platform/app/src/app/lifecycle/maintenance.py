"""Private host-worker bridge, invoked through Docker exec, never through HTTP."""

import argparse
import json
import time
from uuid import UUID

import httpx2 as httpx

from .. import main
from . import catalog, erasure


def inspect(identity):
    path = erasure.directory() / (identity + ".request.json")
    record = json.loads(path.read_text())
    if record["signature"] != erasure.sign(record["payload"]):
        raise ValueError("Invalid maintenance request")
    with main.connect() as conn:
        operation = catalog.read(conn, identity)
    if (
        not operation
        or operation["kind"] != "purge"
        or operation["state"] == "succeeded"
    ):
        raise ValueError("No pending project erasure")
    if any(operation[k] != record["payload"][k] for k in ("project_id", "project")):
        raise ValueError("Maintenance identity mismatch")
    return operation


def operational_storage(operation):
    """Delete project log streams and metric series through private admin APIs."""
    project = operation["project"]
    selectors = [
        "{project=" + json.dumps(project) + "}",
        "{namespace=" + json.dumps("project-" + project) + "}",
        "{platform_project_id=" + json.dumps(operation["project_id"]) + "}",
    ]
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        for match in selectors:
            response = client.post(
                "http://prometheus:9090/api/v1/admin/tsdb/delete_series",
                params={"match[]": match},
            )
            response.raise_for_status()
        response = client.post(
            "http://prometheus:9090/api/v1/admin/tsdb/clean_tombstones"
        )
        response.raise_for_status()
    return True


def verify_loki(operation):
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.get(
            "http://loki:3100/loki/api/v1/query_range",
            params={
                "query": '{job="kubernetes-workloads"}',
                "start": "0",
                "end": str(time.time_ns()),
                "limit": 1,
            },
            headers={"X-Scope-OrgID": operation["project_id"]},
        )
        response.raise_for_status()
        return not response.json()["data"]["result"]


def verify_tempo(operation):
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.get(
            "http://tempo:3200/api/search",
            params={"q": "{}", "limit": 1},
            headers={"X-Scope-OrgID": operation["project_id"]},
        )
        response.raise_for_status()
        return not response.json().get("traces")


def main_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "inspect",
            "operational",
            "verify-traces",
            "verify-logs",
            "receipt",
            "final",
        ],
    )
    parser.add_argument("operation_id", type=UUID)
    args = parser.parse_args()
    identity = str(args.operation_id)
    operation = inspect(identity)
    if args.action == "inspect":
        print(json.dumps(operation, default=str))
    elif args.action == "operational":
        if not operational_storage(operation):
            raise SystemExit(3)
    elif args.action == "verify-logs":
        if not verify_loki(operation):
            raise SystemExit(3)
    elif args.action == "verify-traces":
        if not verify_tempo(operation):
            raise SystemExit(3)
    else:
        if args.action == "final" and operation["step"] != "catalog_removed":
            raise ValueError("The live catalog has not been removed")
        payload = {
            key: operation[key] for key in ("operation_id", "project_id", "project")
        }
        payload["verified"] = True
        erasure.atomic(
            erasure.directory()
            / (
                identity
                + (".final.json" if args.action == "final" else ".receipt.json")
            ),
            payload,
        )


if __name__ == "__main__":
    main_cli()
