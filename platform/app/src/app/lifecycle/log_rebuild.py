"""Rebuild Loki from retained tenants, erasing shared WAL and index remnants.

The host stops Alloy for the entire export/rebuild/verification window. Export
files contain only other tenants and live in the private maintenance directory.
A complete, fsynced export must exist before the host touches Loki storage.
"""

import hashlib
import json
import os
import time

import httpx2 as httpx

from .erasure import directory

PAGE_SIZE = 5000
RETENTION_NS = 7 * 86400 * 1_000_000_000


def selector(labels):
    return (
        "{"
        + ",".join(
            key + "=" + json.dumps(value) for key, value in sorted(labels.items())
        )
        + "}"
    )


def records(client, tenant, labels, start, end):
    """Keep timestamp ties together; fail before erasure if a tie exceeds a page."""
    cursor = start
    while cursor <= end:
        response = client.get(
            "/loki/api/v1/query_range",
            params={
                "query": selector(labels),
                "start": str(cursor),
                "end": str(end),
                "direction": "forward",
                "limit": PAGE_SIZE,
            },
            headers={"X-Scope-OrgID": tenant},
        )
        response.raise_for_status()
        streams = response.json()["data"]["result"]
        values = sorted(
            (entry for stream in streams for entry in stream["values"]),
            key=lambda entry: (int(entry[0]), entry[1]),
        )
        if len(values) < PAGE_SIZE:
            yield from values
            return
        boundary = int(values[-1][0])
        if boundary == cursor:
            raise ValueError("Log timestamp group exceeds safe export page")
        yield from (entry for entry in values if int(entry[0]) < boundary)
        cursor = boundary


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def count(client, tenant, labels, end):
    response = client.get(
        "/loki/api/v1/query",
        params={
            "query": "sum(count_over_time(" + selector(labels) + "[168h]))",
            "time": f"{end // 1_000_000_000}.{end % 1_000_000_000:09d}",
        },
        headers={"X-Scope-OrgID": tenant},
    )
    response.raise_for_status()
    result = response.json()["data"]["result"]
    return sum(int(float(item["value"][1])) for item in result)


def export(conn, operation, client):
    path = directory() / (operation["operation_id"] + ".loki-clean.jsonl")
    if path.exists():
        return
    tenants = ["platform"] + [
        row[0]
        for row in conn.execute(
            "SELECT project_id::text FROM projects WHERE project_id<>%s ORDER BY project_id",
            (operation["project_id"],),
        ).fetchall()
    ]
    end = time.time_ns()
    start = end - RETENTION_NS + 1
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        os.chmod(temporary, 0o600)
        output.write(encoded({"start": start, "end": end, "tenants": tenants}))
        for tenant in tenants:
            response = client.get(
                "/loki/api/v1/series",
                params={"match[]": '{job=~".+"}', "start": str(start), "end": str(end)},
                headers={"X-Scope-OrgID": tenant},
            )
            response.raise_for_status()
            for labels in response.json()["data"]:
                output.write(encoded({"tenant": tenant, "labels": labels}))
                digest = hashlib.sha256()
                total = 0
                for entry in records(client, tenant, labels, start, end):
                    line = encoded({"entry": entry})
                    output.write(line)
                    digest.update(line.encode())
                    total += 1
                # A truncated query is never accepted as a complete export.
                if total != count(client, tenant, labels, end):
                    raise ValueError("Log export count mismatch")
                output.write(encoded({"count": total, "sha256": digest.hexdigest()}))
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def push(client, tenant, labels, values):
    for attempt in range(20):
        response = client.post(
            "/loki/api/v1/push",
            json={"streams": [{"stream": labels, "values": values}]},
            headers={"X-Scope-OrgID": tenant},
        )
        if response.status_code != 429:
            response.raise_for_status()
            return
        time.sleep(min(attempt + 1, 5))
    raise ValueError("Log replay rate limit did not recover")


def restore(operation, client):
    for attempt in range(30):
        try:
            response = client.get("/ready")
            if response.status_code == 200:
                break
        except httpx.RequestError:
            pass
        time.sleep(1)
    else:
        raise ValueError("Rebuilt log storage is not ready")
    path = directory() / (operation["operation_id"] + ".loki-clean.jsonl")
    with path.open(encoding="utf-8") as source:
        bounds = json.loads(next(source))
        batch, size, stream = [], 0, None
        for line in source:
            row = json.loads(line)
            if "tenant" in row:
                stream = row
            elif "entry" in row:
                batch.append(row["entry"])
                size += len(line.encode())
                if size >= 512 * 1024:
                    push(client, stream["tenant"], stream["labels"], batch)
                    batch, size = [], 0
            else:
                if batch:
                    push(client, stream["tenant"], stream["labels"], batch)
                    batch, size = [], 0
                digest, total = hashlib.sha256(), 0
                for entry in records(
                    client,
                    stream["tenant"],
                    stream["labels"],
                    bounds["start"],
                    bounds["end"],
                ):
                    digest.update(encoded({"entry": entry}).encode())
                    total += 1
                if total != row["count"] or digest.hexdigest() != row["sha256"]:
                    raise ValueError("Retained log verification failed")


def client():
    return httpx.Client(base_url="http://loki:3100", timeout=60, trust_env=False)
