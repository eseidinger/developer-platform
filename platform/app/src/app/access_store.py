"""PostgreSQL access catalog, versioned resources, immutable policies and durable work."""

import hashlib
import json
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

LOCK = 731910
KINDS = {
    "group",
    "policy",
    "policy-revision",
    "human-request",
    "membership",
    "service-access",
    "governance",
}


def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS hosted_access_resources (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, project TEXT NOT NULL REFERENCES projects(name),
        name TEXT NOT NULL, state TEXT NOT NULL, version BIGINT NOT NULL DEFAULT 1,
        spec JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(kind, project, name))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hosted_access_principals (
        issuer TEXT NOT NULL, subject TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
        PRIMARY KEY(issuer, subject), CHECK(kind IN ('user', 'service')))""")
    conn.execute(
        "ALTER TABLE hosted_access_principals ADD COLUMN IF NOT EXISTS display_name TEXT"
    )
    conn.execute("""CREATE TABLE IF NOT EXISTS hosted_access_operations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(), resource_id TEXT NOT NULL,
        version BIGINT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
        attempts INT NOT NULL DEFAULT 0, error_code TEXT, envelope_version INT NOT NULL DEFAULT 1,
        actor_issuer TEXT NOT NULL, actor_subject TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hosted_access_idempotency (
        project TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, digest TEXT NOT NULL,
        resource_id TEXT NOT NULL, PRIMARY KEY(project, kind, key))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hosted_access_metadata (
        key TEXT PRIMARY KEY, value JSONB NOT NULL)""")
    conn.execute("""INSERT INTO hosted_access_metadata(key, value) VALUES ('generation', '1')
        ON CONFLICT(key) DO NOTHING""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hosted_access_replicas (
        id TEXT PRIMARY KEY, generation BIGINT NOT NULL, observed_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS hosted_access_operations_pending ON hosted_access_operations(state, updated_at)"
    )
    conn.execute("""REVOKE ALL ON hosted_access_resources, hosted_access_principals,
        hosted_access_operations, hosted_access_idempotency, hosted_access_metadata,
        hosted_access_replicas FROM PUBLIC""")


@contextmanager
def locked(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        yield


def project_exists(conn, project):
    row = conn.execute(
        "SELECT status FROM projects WHERE name=%s", (project,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown project")
    if row[0] == "retired":
        raise HTTPException(409, "Project is retired")


def unpack(row):
    if row is None:
        return None
    return dict(
        zip(
            (
                "id",
                "kind",
                "project",
                "name",
                "state",
                "version",
                "spec",
                "created_at",
                "updated_at",
            ),
            row,
        )
    )


COLUMNS = "id, kind, project, name, state, version, spec, created_at, updated_at"


def get(conn, resource_id, project=None, kind=None):
    row = unpack(
        conn.execute(
            "SELECT " + COLUMNS + " FROM hosted_access_resources WHERE id=%s",
            (resource_id,),
        ).fetchone()
    )
    if (
        not row
        or (project is not None and row["project"] != project)
        or (kind and row["kind"] != kind)
    ):
        raise HTTPException(404, "Unknown access resource")
    return row


def by_name(conn, kind, project, name):
    return unpack(
        conn.execute(
            "SELECT "
            + COLUMNS
            + " FROM hosted_access_resources WHERE kind=%s AND project=%s AND name=%s",
            (kind, project, name),
        ).fetchone()
    )


def listing(conn, kind=None, project=None):
    return [
        unpack(row)
        for row in conn.execute(
            "SELECT "
            + COLUMNS
            + """ FROM hosted_access_resources
        WHERE (%s::text IS NULL OR kind=%s) AND (%s::text IS NULL OR project=%s) ORDER BY created_at, id""",
            (kind, kind, project, project),
        ).fetchall()
    ]


def bump(conn):
    return conn.execute("""UPDATE hosted_access_metadata SET value=to_jsonb((value::text)::bigint + 1)
        WHERE key='generation' RETURNING value""").fetchone()[0]


def generation(conn):
    return conn.execute(
        "SELECT value FROM hosted_access_metadata WHERE key='generation'"
    ).fetchone()[0]


def create(conn, kind, project, name, spec, state="pending", resource_id=None):
    if kind not in KINDS:
        raise ValueError("Unsupported access resource")
    if by_name(conn, kind, project, name):
        raise HTTPException(409, "Access resource name already exists")
    prefixes = {
        "group": "grp",
        "policy": "pol",
        "policy-revision": "rev",
        "membership": "mem",
        "human-request": "req",
        "service-access": "svc",
        "governance": "gov",
    }
    rid = resource_id or prefixes[kind] + "_" + uuid4().hex
    conn.execute(
        """INSERT INTO hosted_access_resources(id, kind, project, name, spec, state)
        VALUES (%s,%s,%s,%s,%s,%s)""",
        (rid, kind, project, name, Jsonb(spec), state),
    )
    bump(conn)
    return get(conn, rid)


def update(conn, row, *, spec=None, state=None):
    updated = unpack(
        conn.execute(
            """UPDATE hosted_access_resources SET spec=%s, state=%s,
        version=version+1, updated_at=now() WHERE id=%s AND version=%s RETURNING """
            + COLUMNS,
            (
                Jsonb(row["spec"] if spec is None else spec),
                state or row["state"],
                row["id"],
                row["version"],
            ),
        ).fetchone()
    )
    if not updated:
        raise HTTPException(409, "Resource changed concurrently")
    bump(conn)
    return updated


def check_version(row, if_match):
    if if_match is None:
        raise HTTPException(428, "If-Match is required")
    if if_match != '"' + str(row["version"]) + '"':
        raise HTTPException(412, "Access resource version changed")


def replay(conn, project, kind, key, body):
    if not key or len(key) > 128 or not all(32 < ord(c) < 127 for c in key):
        raise HTTPException(422, "A bounded printable Idempotency-Key is required")
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    row = conn.execute(
        """SELECT digest, resource_id FROM hosted_access_idempotency
        WHERE project=%s AND kind=%s AND key=%s""",
        (project, kind, key),
    ).fetchone()
    if row and row[0] != digest:
        raise HTTPException(409, "Idempotency key was reused with different content")
    return get(conn, row[1], project) if row else None, digest


def remember(conn, row, key, digest, kind=None):
    conn.execute(
        """INSERT INTO hosted_access_idempotency(project, kind, key, digest, resource_id)
        VALUES (%s,%s,%s,%s,%s)""",
        (row["project"], kind or row["kind"], key, digest, row["id"]),
    )


def enqueue(conn, row, action, actor):
    oid = conn.execute(
        """INSERT INTO hosted_access_operations(resource_id, version, action, actor_issuer, actor_subject)
        VALUES (%s,%s,%s,%s,%s) RETURNING id""",
        (row["id"], row["version"], action, actor.issuer, actor.subject),
    ).fetchone()[0]
    return str(oid)


def resolve_groups(conn, project, refs):
    found = []
    for ref in refs:
        group = by_name(conn, "group", project, ref)
        if group is None:
            group = get(conn, ref, project, "group")
        if group["state"] != "active":
            raise HTTPException(409, "Referenced group is not active")
        found.append(group["id"])
    if len(set(found)) != len(found):
        raise HTTPException(422, "Group references resolve to duplicate IDs")
    return found


def application(conn, project, name, component=None):
    project_exists(conn, project)
    row = conn.execute(
        """SELECT a.application_id, p.spec FROM project_applications a
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id WHERE p.name=%s AND a.name=%s AND e.name='default'""",
        (project, name),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown application")
    spec = row[1] or {}
    components = spec.get("components")
    if components is None:
        raise HTTPException(
            409, "Hosted access requires a v1alpha2 application with a public component"
        )
    public = [
        c
        for c in components
        if c.get("exposure") == "public" and c["type"] == "service"
    ]
    if len(public) != 1 or (component and public[0]["name"] != component):
        raise HTTPException(409, "Policy must target the single public component")
    return str(row[0]), public[0]


def principal(conn, issuer, subject, kind="user", principal_id=None):
    rid = principal_id or "prn_" + uuid4().hex
    row = conn.execute(
        """INSERT INTO hosted_access_principals(issuer, subject, id, kind)
        VALUES (%s,%s,%s,%s) ON CONFLICT(issuer, subject) DO UPDATE SET subject=excluded.subject
        RETURNING id, kind""",
        (issuer, subject, rid, kind),
    ).fetchone()
    if row[1] != kind or (principal_id and row[0] != principal_id):
        raise HTTPException(409, "Principal identity conflict")
    return row[0]


def with_principal_names(conn, resources):
    """Enrich authorized rows without changing stored specs or resource versions.

    Issuer and subject together identify a person. Names are presentation only;
    they never participate in authorization and may be unavailable until login.
    """
    ids = list({row["spec"]["principalId"] for row in resources})
    if not ids:
        return resources
    names = dict(
        conn.execute(
            """SELECT h.id, COALESCE(p.display_name, h.display_name)
            FROM hosted_access_principals h
            LEFT JOIN platform_principals p ON p.issuer=h.issuer AND p.subject=h.subject
            WHERE h.id=ANY(%s)""",
            (ids,),
        ).fetchall()
    )
    return [
        {
            **row,
            "spec": {
                **row["spec"],
                "displayName": names.get(row["spec"]["principalId"]),
            },
        }
        for row in resources
    ]


def enroll(conn, policy, issuer, subject, display_name=None):
    pid = principal(conn, issuer, subject)
    if display_name:
        conn.execute(
            "UPDATE hosted_access_principals SET display_name=%s WHERE issuer=%s AND subject=%s",
            (display_name, issuer, subject),
        )
    name = policy["id"] + ":" + pid
    request = by_name(conn, "human-request", policy["project"], name)
    if request and request["state"] == "expired":
        request = update(
            conn,
            request,
            state="pending",
            spec={
                **request["spec"],
                "expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
        )
    if not request:
        request = create(
            conn,
            "human-request",
            policy["project"],
            name,
            {
                "policyId": policy["id"],
                "principalId": pid,
                "issuer": issuer,
                "subject": subject,
                "expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
        )
    return pid, request


def memberships(
    conn, project, policy_id, principal_id, group_ids, issuer, subject, actor
):
    rows = []
    for gid in group_ids:
        name = policy_id + ":" + principal_id + ":" + gid
        row = by_name(conn, "membership", project, name)
        if not row:
            row = create(
                conn,
                "membership",
                project,
                name,
                {
                    "policyId": policy_id,
                    "principalId": principal_id,
                    "groupId": gid,
                    "issuer": issuer,
                    "subject": subject,
                },
                "provisioning",
            )
        elif row["state"] not in {"active", "provisioning"}:
            row = update(conn, row, state="provisioning")
        if row["state"] == "provisioning":
            enqueue(conn, row, "membership.grant", actor)
        rows.append(row)
    return rows


def nonce():
    return secrets.token_hex(16)


def retire(conn, project, actor):
    for row in listing(conn):
        if row["project"] != project and row["spec"].get("providerProject") != project:
            continue
        if row["kind"] in {"membership", "service-access", "policy", "group"} and row[
            "state"
        ] not in {"revoked", "revocation-pending"}:
            row = update(conn, row, state="revocation-pending")
            enqueue(conn, row, row["kind"] + ".revoke", actor)
        elif row["kind"] == "human-request" and row["state"] == "pending":
            update(conn, row, state="cancelled")


def prune(conn):
    now = datetime.now(UTC)
    expired = []
    for row in listing(conn, "human-request"):
        if (
            row["state"] == "pending"
            and datetime.fromisoformat(row["spec"]["expiresAt"]) <= now
        ):
            expired.append(update(conn, row, state="expired"))
    conn.execute("""DELETE FROM hosted_access_idempotency WHERE resource_id IN (
        SELECT id FROM hosted_access_resources WHERE updated_at<now()-interval '90 days'
        AND ((kind='human-request' AND state IN ('approved','rejected','cancelled','expired'))
            OR (kind='membership' AND state='revoked')))""")
    conn.execute("""DELETE FROM hosted_access_resources WHERE updated_at<now()-interval '90 days'
        AND ((kind='human-request' AND state IN ('approved','rejected','cancelled','expired'))
            OR (kind='membership' AND state='revoked')) RETURNING id""")
    conn.execute("""DELETE FROM hosted_access_operations WHERE NOT EXISTS (
        SELECT 1 FROM hosted_access_resources WHERE id=hosted_access_operations.resource_id)""")
    conn.execute(
        """DELETE FROM hosted_access_replicas WHERE observed_at<now()-interval '1 day'"""
    )
    return expired
