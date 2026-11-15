"""Lifecycle state and encrypted recovery points, keyed by immutable project IDs."""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

LOCK = 731904
SNAPSHOT_AAD = b"platform.eseidinger.de/v1/retirement"
TOKEN_SECONDS = 900


def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS project_recovery_points (
        project_id UUID PRIMARY KEY REFERENCES projects(project_id),
        encrypted_snapshot TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS project_lifecycle_operations (
        operation_id UUID PRIMARY KEY, project_id UUID NOT NULL, project TEXT NOT NULL,
        action TEXT NOT NULL CHECK(action IN ('retire','restore','purge')),
        state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','blocked','failed','succeeded')),
        step TEXT NOT NULL DEFAULT 'prepare', actor JSONB NOT NULL, intent JSONB NOT NULL,
        result JSONB NOT NULL DEFAULT '{}', error_code TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at TIMESTAMPTZ)""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS project_lifecycle_one_active
        ON project_lifecycle_operations(project_id) WHERE state IN ('queued','running','blocked')""")
    conn.execute(
        "REVOKE ALL ON project_recovery_points,project_lifecycle_operations FROM PUBLIC"
    )


def encryption_key():
    return hashlib.sha256(
        (os.environ["DATABASE_KEY"] + ":project-recovery:v1").encode()
    ).digest()


def seal(project_id, snapshot):
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(jsonable_encoder(snapshot), sort_keys=True).encode()
    encrypted = AESGCM(encryption_key()).encrypt(
        nonce, plaintext, SNAPSHOT_AAD + str(project_id).encode()
    )
    return base64.b64encode(nonce + encrypted).decode()


def unseal(project_id, encrypted):
    value = base64.b64decode(encrypted, validate=True)
    return json.loads(
        AESGCM(encryption_key()).decrypt(
            value[:12], value[12:], SNAPSHOT_AAD + str(project_id).encode()
        )
    )


def project(conn, name):
    row = conn.execute(
        "SELECT project_id::text,status,spec,updated_at FROM projects WHERE name=%s FOR UPDATE",
        (name,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown project")
    return {
        "project_id": row[0],
        "status": row[1],
        "spec": row[2],
        "updated_at": row[3].isoformat(),
    }


def issue_token(scope, now=None):
    expires = int((now or datetime.now(UTC)).timestamp()) + TOKEN_SECONDS
    message = json.dumps(
        jsonable_encoder(
            {
                "scope_sha256": hashlib.sha256(
                    json.dumps(jsonable_encoder(scope), sort_keys=True).encode()
                ).hexdigest(),
                "expires": expires,
            }
        ),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(message).decode()
    signature = hmac.new(encryption_key(), message, hashlib.sha256).hexdigest()
    return encoded + "." + signature


def check_token(token, scope, now=None):
    try:
        encoded, signature = token.split(".")
        message = base64.urlsafe_b64decode(encoded)
        expected = hmac.new(encryption_key(), message, hashlib.sha256).hexdigest()
        value = json.loads(message)
        if (
            not hmac.compare_digest(signature, expected)
            or value["expires"] < int((now or datetime.now(UTC)).timestamp())
            or value["scope_sha256"]
            != hashlib.sha256(
                json.dumps(jsonable_encoder(scope), sort_keys=True).encode()
            ).hexdigest()
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            409, {"code": "scope_changed", "message": "Request a new lifecycle preview"}
        ) from None


def enqueue(conn, name, action, body, principal, scope):
    if body.confirm_name != name or str(body.confirm_project_id) != scope["project_id"]:
        raise HTTPException(400, "Confirmation must identify the project name and UUID")
    # Compare the replay before recomputing scope: the first request fences the
    # project, which intentionally changes its state and preview fingerprint.
    existing = conn.execute(
        """SELECT operation_id::text,action,intent,state FROM project_lifecycle_operations
        WHERE project_id=%s AND state IN ('queued','running','blocked')""",
        (scope["project_id"],),
    ).fetchone()
    intent = body.model_dump(mode="json")
    if existing:
        if existing[1] == action and existing[2] == intent:
            return accepted(existing[0], existing[3], action)
        raise HTTPException(409, "Another lifecycle operation is active")
    check_token(body.scope_token, scope)
    if scope["blockers"]:
        raise HTTPException(
            409, {"code": "lifecycle_blocked", "blockers": scope["blockers"]}
        )
    identity = str(uuid4())
    conn.execute(
        """INSERT INTO project_lifecycle_operations(operation_id,project_id,project,action,actor,intent)
        VALUES(%s,%s,%s,%s,%s,%s)""",
        (
            identity,
            scope["project_id"],
            name,
            action,
            Jsonb(jsonable_encoder(principal.__dict__)),
            Jsonb(intent),
        ),
    )
    conn.execute(
        "UPDATE projects SET status=%s,updated_at=now() WHERE project_id=%s",
        (
            {"retire": "retiring", "restore": "restoring", "purge": "purging"}[action],
            scope["project_id"],
        ),
    )
    return accepted(identity, "queued", action)


def accepted(identity, state, kind):
    return {
        "operation_id": identity,
        "kind": kind,
        "state": state,
        "status_url": "/v1/operations/" + identity,
    }


def read(conn, identity):
    row = conn.execute(
        """SELECT operation_id::text,project_id::text,project,action,state,step,result,error_code,created_at,updated_at
        FROM project_lifecycle_operations WHERE operation_id=%s""",
        (identity,),
    ).fetchone()
    if not row:
        return None
    return dict(
        zip(
            (
                "operation_id",
                "project_id",
                "project",
                "kind",
                "state",
                "step",
                "result",
                "error_code",
                "created_at",
                "updated_at",
            ),
            row,
        )
    )


def expire_receipts(conn):
    """Erase the final receipt and its host handoff files after 24 hours."""
    from .erasure import directory

    expired = conn.execute(
        "SELECT operation_id::text FROM project_lifecycle_operations WHERE action='purge' AND state='succeeded' AND completed_at<%s",
        (datetime.now(UTC) - timedelta(hours=24),),
    ).fetchall()
    for (identity,) in expired:
        for suffix in (".request.json", ".receipt.json", ".final.json"):
            (directory() / (identity + suffix)).unlink(missing_ok=True)
        conn.execute(
            "DELETE FROM project_lifecycle_operations WHERE operation_id=%s",
            (identity,),
        )


def retirement_actor(conn, identity, principal):
    """A retiring caller may observe its own receipt after project roles revoke."""
    return bool(
        conn.execute(
            "SELECT 1 FROM project_lifecycle_operations WHERE operation_id=%s AND action='retire' AND actor->>'issuer'=%s AND actor->>'subject'=%s",
            (identity, principal.issuer, principal.subject),
        ).fetchone()
    )
