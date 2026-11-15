"""Authenticated host-maintenance requests and receipts for complete erasure.

The API has no Docker socket or restic password. A privileged host worker owns
backend compaction and backup removal and attests only verified completion.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path

from .catalog import encryption_key


def directory():
    return Path(
        os.environ.get("PLATFORM_MAINTENANCE_DIR", "/var/lib/platform-maintenance")
    )


def sign(payload):
    return hmac.new(
        encryption_key(),
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()


def atomic(path, payload):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump({"payload": payload, "signature": sign(payload)}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def request(operation):
    root = directory()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / (operation["operation_id"] + ".request.json")
    if not path.exists():
        atomic(
            path,
            {
                "operation_id": operation["operation_id"],
                "project_id": operation["project_id"],
                "project": operation["project"],
            },
        )


def verified_receipt(operation, final=False):
    path = directory() / (
        operation["operation_id"] + (".final.json" if final else ".receipt.json")
    )
    if not path.exists():
        return False
    record = json.loads(path.read_text())
    payload = record["payload"]
    if not hmac.compare_digest(record["signature"], sign(payload)):
        return False
    expected = {
        "operation_id": operation["operation_id"],
        "project_id": operation["project_id"],
        "project": operation["project"],
    }
    return (
        all(payload.get(k) == v for k, v in expected.items())
        and payload.get("verified") is True
    )
