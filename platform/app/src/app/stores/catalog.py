"""Durable desired/observed lifecycle. IDs, not names, identify resources and grants."""

import hashlib
import hmac
import os
from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

HUMAN_LIFETIME = timedelta(hours=24)
APPLICATION_ROTATION = timedelta(days=30)
ROTATION_OVERLAP = timedelta(hours=1)


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS store_control (
        singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
        recovery_required BOOLEAN NOT NULL DEFAULT false)""")
    conn.execute(
        "INSERT INTO store_control(singleton) VALUES(true) ON CONFLICT DO NOTHING"
    )
    conn.execute(
        "ALTER TABLE store_control ADD COLUMN IF NOT EXISTS backup_until TIMESTAMPTZ"
    )
    conn.execute("REVOKE ALL ON store_control FROM PUBLIC")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_project_retirements (
        project TEXT PRIMARY KEY REFERENCES projects(name) ON DELETE CASCADE, retired_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("REVOKE ALL ON store_project_retirements FROM PUBLIC")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_resources (
        resource_id UUID PRIMARY KEY, owner_project TEXT NOT NULL REFERENCES projects(name),
        name TEXT NOT NULL, provider TEXT NOT NULL CHECK(provider IN ('postgresql','s3','opensearch','neo4j','qdrant')),
        extensions JSONB NOT NULL DEFAULT '[]', quota_bytes BIGINT NOT NULL CHECK(quota_bytes>0),
        state TEXT NOT NULL CHECK(state IN ('active','retired','purging','purged')),
        observed_state TEXT NOT NULL DEFAULT 'pending', error_code TEXT,
        version BIGINT NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), used_bytes BIGINT,
        usage_measured_at TIMESTAMPTZ, usage_attempt_at TIMESTAMPTZ,
        usage_error BOOLEAN NOT NULL DEFAULT false, purge_backup_version BIGINT,
        purge_backup_snapshot TEXT)""")
    conn.execute("""ALTER TABLE store_resources ADD COLUMN IF NOT EXISTS used_bytes BIGINT,
        ADD COLUMN IF NOT EXISTS usage_measured_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS usage_attempt_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS usage_error BOOLEAN NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS purge_backup_version BIGINT,
        ADD COLUMN IF NOT EXISTS purge_backup_snapshot TEXT,
        ADD COLUMN IF NOT EXISTS configuration JSONB NOT NULL DEFAULT '{}'""")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_instances (
        resource_id UUID PRIMARY KEY REFERENCES store_resources(resource_id),
        host INET NOT NULL, port INTEGER NOT NULL CHECK(port=7687))""")
    conn.execute("REVOKE ALL ON store_instances FROM PUBLIC")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS store_neo4j_project
        ON store_resources(owner_project) WHERE provider='neo4j' AND state<>'purged'""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS store_resource_names
        ON store_resources(owner_project,name) WHERE state<>'purged'""")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_grants (
        grant_id UUID PRIMARY KEY, resource_id UUID NOT NULL REFERENCES store_resources(resource_id),
        kind TEXT NOT NULL CHECK(kind IN ('human','binding')),
        issuer TEXT, subject TEXT, consumer_project TEXT REFERENCES projects(name), component TEXT,
        mode TEXT NOT NULL CHECK(mode IN ('read-only','read-write')),
        state TEXT NOT NULL CHECK(state IN ('pending','active','rejected','revoked')),
        observed_state TEXT NOT NULL DEFAULT 'pending', version BIGINT NOT NULL DEFAULT 1,
        requested_by TEXT NOT NULL, approved_by TEXT, error_code TEXT, bound_once BOOLEAN NOT NULL DEFAULT false, delivered_credential_id UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK((kind='human' AND issuer IS NOT NULL AND subject IS NOT NULL
                  AND consumer_project IS NULL AND component IS NULL)
            OR (kind='binding' AND issuer IS NULL AND subject IS NULL
                  AND consumer_project IS NOT NULL AND component IS NOT NULL)))""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS store_human_grant_identity
        ON store_grants(resource_id,issuer,subject) WHERE kind='human' AND state IN ('pending','active')""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS store_binding_identity
        ON store_grants(resource_id,consumer_project,component) WHERE kind='binding' AND state IN ('pending','active')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_credentials (
        credential_id UUID PRIMARY KEY, grant_id UUID NOT NULL REFERENCES store_grants(grant_id),
        grant_version BIGINT NOT NULL, relay_port INTEGER, mode TEXT NOT NULL CHECK(mode IN ('read-only','read-write')),
        state TEXT NOT NULL CHECK(state IN ('issuing','active','retiring','revoked')),
        issued_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
        handover_deadline TIMESTAMPTZ, observed_state TEXT NOT NULL DEFAULT 'pending', error_code TEXT,
        UNIQUE(credential_id,grant_id))""")
    conn.execute(
        "ALTER TABLE store_credentials ADD COLUMN IF NOT EXISTS admission_sha256 TEXT"
    )
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS store_live_relay_ports
        ON store_credentials(relay_port) WHERE state<>'revoked' AND relay_port IS NOT NULL""")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_human_keys (
        issuer TEXT NOT NULL, subject TEXT NOT NULL, public_key TEXT NOT NULL, fingerprint TEXT UNIQUE NOT NULL,
        PRIMARY KEY(issuer,subject))""")
    conn.execute("REVOKE ALL ON store_human_keys FROM PUBLIC")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS store_credentials_expiry ON store_credentials(expires_at) WHERE state<>'revoked'"
    )
    conn.execute(
        "REVOKE ALL ON store_resources,store_grants,store_credentials FROM PUBLIC"
    )
    conn.execute("""CREATE TABLE IF NOT EXISTS store_console_sessions (
        native_access_key TEXT PRIMARY KEY CHECK(length(native_access_key) BETWEEN 16 AND 128),
        credential_id UUID NOT NULL REFERENCES store_credentials(credential_id),
        token_sha256 TEXT NOT NULL CHECK(token_sha256 ~ '^[a-f0-9]{64}$'),
        expires_at TIMESTAMPTZ NOT NULL)""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS store_console_sessions_lease ON store_console_sessions(credential_id,expires_at)"
    )
    conn.execute("REVOKE ALL ON store_console_sessions FROM PUBLIC")


def console_sessions(conn, credential_id):
    rows = conn.execute(
        """SELECT native_access_key,token_sha256,expires_at FROM store_console_sessions
        WHERE credential_id=%s AND expires_at>now() ORDER BY expires_at LIMIT 16""",
        (credential_id,),
    ).fetchall()
    return {
        key: {"token_sha256": digest, "expires_at": expiry}
        for key, digest, expiry in rows
    }


def _object(conn, table, field, identity, lock=False):
    # Table and field are module-owned literals, never caller input.
    row = conn.execute(
        f"SELECT row_to_json(item) FROM {table} item WHERE {field}=%s"
        + (" FOR UPDATE" if lock else ""),
        (identity,),
    ).fetchone()
    if not row:
        raise NotFound()
    return row[0]


def resource(conn, resource_id, lock=False):
    return _object(conn, "store_resources", "resource_id", resource_id, lock)


def grant(conn, grant_id, lock=False):
    return _object(conn, "store_grants", "grant_id", grant_id, lock)


def assert_version(row, version):
    if row["version"] != version:
        raise Conflict("The resource changed; refresh before retrying")


def active_project(conn, project):
    row = conn.execute(
        """SELECT p.status,EXISTS(SELECT 1 FROM store_project_retirements s WHERE s.project=p.name)
        FROM projects p WHERE name=%s FOR UPDATE""",
        (project,),
    ).fetchone()
    if not row or row[0] == "retired" or row[1]:
        raise Conflict("Project is not active")


def create_resource(conn, project, body):
    active_project(conn, project)
    if (
        body.provider == "neo4j"
        and conn.execute(
            "SELECT 1 FROM store_resources WHERE owner_project=%s AND provider='neo4j' AND state<>'purged'",
            (project,),
        ).fetchone()
    ):
        raise Conflict(
            "Only one retained Neo4j Community resource is supported per project"
        )
    resource_id = uuid4()
    conn.execute(
        """INSERT INTO store_resources(resource_id,owner_project,name,provider,extensions,quota_bytes,configuration,state)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'active')""",
        (
            resource_id,
            project,
            body.name,
            body.provider,
            Jsonb(body.extensions),
            body.quota_bytes,
            Jsonb(
                body.configuration.model_dump()
                if body.configuration is not None
                else {}
            ),
        ),
    )
    return resource(conn, resource_id)


def check_grant_capacity(conn, resource_id):
    count = conn.execute(
        """SELECT count(*) FROM store_grants WHERE resource_id=%s
        AND state IN ('pending','active')""",
        (resource_id,),
    ).fetchone()[0]
    if count >= 64:
        raise Conflict("The resource's 64 active/pending grants allocation is full")


def create_human_grant(conn, res, body, actor):
    from .neo4j import require_mode

    require_mode(res["provider"], body.mode)
    if res["state"] != "active":
        raise Conflict("Resource is not active")
    active_project(conn, res["owner_project"])
    check_grant_capacity(conn, res["resource_id"])
    identity = uuid4()
    conn.execute(
        """INSERT INTO store_grants(grant_id,resource_id,kind,issuer,subject,mode,state,requested_by,approved_by)
        VALUES (%s,%s,'human',%s,%s,%s,'active',%s,%s)""",
        (
            identity,
            res["resource_id"],
            body.issuer,
            body.subject,
            body.mode,
            actor,
            actor,
        ),
    )
    return grant(conn, identity)


def request_binding(conn, consumer, body, actor):
    active_project(conn, consumer)
    res = resource(conn, body.resource_id, lock=True)
    from .neo4j import require_mode

    require_mode(res["provider"], body.mode)
    active_project(conn, res["owner_project"])
    if res["state"] != "active":
        raise Conflict("Resource is not active")
    check_grant_capacity(conn, res["resource_id"])
    identity = uuid4()
    own = consumer == res["owner_project"]
    conn.execute(
        """INSERT INTO store_grants(grant_id,resource_id,kind,consumer_project,component,mode,state,
        requested_by,approved_by) VALUES (%s,%s,'binding',%s,%s,%s,%s,%s,%s)""",
        (
            identity,
            res["resource_id"],
            consumer,
            body.component,
            body.mode,
            "active" if own else "pending",
            actor,
            actor if own else None,
        ),
    )
    return grant(conn, identity)


def approve(conn, row, approve_request, actor):
    assert_version(row, approve_request.version)
    res = resource(conn, row["resource_id"], lock=True)
    if (
        row["kind"] != "binding"
        or row["state"] != "pending"
        or res["state"] != "active"
    ):
        raise Conflict("Binding is not pending approval on an active resource")
    active_project(conn, res["owner_project"])
    active_project(conn, row["consumer_project"])
    conn.execute(
        """UPDATE store_grants SET state=%s,approved_by=%s,version=version+1,updated_at=now()
        WHERE grant_id=%s""",
        ("active" if approve_request.approve else "rejected", actor, row["grant_id"]),
    )
    return grant(conn, row["grant_id"])


def retire(conn, row, version):
    assert_version(row, version)
    if row["state"] != "active":
        raise Conflict("Only active resources can be retired")
    conn.execute(
        """UPDATE store_resources SET state='retired',observed_state='pending',
        version=version+1,updated_at=now() WHERE resource_id=%s""",
        (row["resource_id"],),
    )
    conn.execute(
        """UPDATE store_grants SET state='revoked',observed_state='pending',version=version+1,
        updated_at=now() WHERE resource_id=%s AND state IN ('pending','active')""",
        (row["resource_id"],),
    )
    return resource(conn, row["resource_id"])


def request_purge(conn, row, body):
    assert_version(row, body.version)
    if (
        str(body.confirm_resource_id) != row["resource_id"]
        or body.confirm_owner_project != row["owner_project"]
    ):
        raise Conflict("Purge confirmation does not identify this resource and owner")
    if row["state"] != "retired" or row["observed_state"] != "retired":
        raise Conflict("Purge requires retirement and completed access cleanup")
    held = conn.execute(
        """SELECT 1 FROM store_credentials c JOIN store_grants g USING(grant_id)
        WHERE g.resource_id=%s AND c.state<>'revoked' LIMIT 1""",
        (row["resource_id"],),
    ).fetchone()
    if held:
        raise Conflict("Credential cleanup is incomplete")
    conn.execute(
        """UPDATE store_resources SET state='purging',observed_state='pending',
        version=version+1,updated_at=now() WHERE resource_id=%s""",
        (row["resource_id"],),
    )
    return resource(conn, row["resource_id"])


def issue(conn, row):
    from . import recovery

    if recovery.required(conn):
        raise Conflict("Named-store recovery reconciliation is required")
    res = resource(conn, row["resource_id"], lock=True)
    from .neo4j import require_mode

    require_mode(res["provider"], row["mode"])
    if (
        row["state"] != "active"
        or res["state"] != "active"
        or res["observed_state"] != "active"
    ):
        raise Conflict("Grant and resource must be active and provisioned")
    active_project(conn, res["owner_project"])
    if row["kind"] == "binding":
        active_project(conn, row["consumer_project"])
    outstanding = conn.execute(
        """SELECT count(*) FROM store_credentials WHERE grant_id=%s
        AND state<>'revoked' AND expires_at>now()""",
        (row["grant_id"],),
    ).fetchone()[0]
    if outstanding >= 24:
        raise Conflict(
            "Too many outstanding credential generations; wait for expiry or revoke access"
        )
    if row["kind"] == "human":
        leases = conn.execute(
            """SELECT count(*) FROM store_credentials c JOIN store_grants g USING(grant_id)
            WHERE g.kind='human' AND g.issuer=%s AND g.subject=%s AND g.state='active'
            AND c.state<>'revoked' AND c.grant_version=g.version AND c.expires_at>now()""",
            (row["issuer"], row["subject"]),
        ).fetchone()[0]
        if leases >= 64:
            raise Conflict(
                "The human's 64 private credential leases allocation is full; wait for expiry or revoke access"
            )
    # Every credential uses a lease port, including application bindings.
    free = conn.execute("""SELECT port FROM generate_series(20000,20511) port WHERE NOT EXISTS(
        SELECT 1 FROM store_credentials c WHERE c.relay_port=port AND c.state<>'revoked')
        ORDER BY port LIMIT 1""").fetchone()
    if not free:
        raise Conflict("Private access lease capacity is full; wait for cleanup")
    relay_port = free[0]
    identity = uuid4()
    lifetime = (
        HUMAN_LIFETIME
        if row["kind"] == "human"
        else APPLICATION_ROTATION + ROTATION_OVERLAP
    )
    if row["kind"] == "binding":
        # Persist the FIRST replacement deadline. Retries cannot extend it.
        conn.execute(
            """UPDATE store_credentials SET state='retiring',handover_deadline=COALESCE(handover_deadline,now()+%s),
            expires_at=LEAST(expires_at,COALESCE(handover_deadline,now()+%s))
            WHERE grant_id=%s AND state IN ('active','retiring')""",
            (ROTATION_OVERLAP, ROTATION_OVERLAP, row["grant_id"]),
        )
    conn.execute(
        """INSERT INTO store_credentials(credential_id,grant_id,grant_version,mode,state,expires_at,relay_port)
        VALUES (%s,%s,%s,%s,'issuing',now()+%s,%s)""",
        (identity, row["grant_id"], row["version"], row["mode"], lifetime, relay_port),
    )
    if res["provider"] == "neo4j":
        conn.execute(
            "UPDATE store_credentials SET admission_sha256=%s WHERE credential_id=%s",
            (hashlib.sha256(secret_for(identity).encode()).hexdigest(), identity),
        )
    return _object(conn, "store_credentials", "credential_id", identity)


def secret_for(credential_id):
    key = os.environ.get("DATABASE_KEY", "")
    if len(key) < 32:
        raise RuntimeError("Managed credential key is unavailable")
    return hmac.new(
        key.encode(),
        ("store-credential-v1:" + str(credential_id)).encode(),
        hashlib.sha256,
    ).hexdigest()


def identifier(resource_id):
    from uuid import UUID

    return "resource_" + UUID(str(resource_id)).hex


def login(credential_id):
    from uuid import UUID

    return "credential_" + UUID(str(credential_id)).hex


def lock(conn):
    # Same lifecycle lock as deployments/retirement: serialize authority checks
    # with changes to the desired workload and avoid provider-side races.
    conn.execute("SELECT pg_advisory_xact_lock(731904)")


def revoke(conn, row, version):
    assert_version(row, version)
    conn.execute(
        """UPDATE store_grants SET state='revoked',observed_state='pending',version=version+1,
        updated_at=now() WHERE grant_id=%s""",
        (row["grant_id"],),
    )
    return grant(conn, row["grant_id"])


def change_mode(conn, row, body, actor):
    from .neo4j import require_mode

    require_mode(resource(conn, row["resource_id"])["provider"], body.mode)
    assert_version(row, body.version)
    if row["state"] != "active":
        raise Conflict("Grant is not active")
    # Only an owning-project administrator may call this operation. Existing
    # generations become stale immediately, including on scope increase.
    conn.execute(
        """UPDATE store_grants SET mode=%s,approved_by=%s,version=version+1,
        observed_state='pending',updated_at=now() WHERE grant_id=%s""",
        (body.mode, actor, row["grant_id"]),
    )
    return grant(conn, row["grant_id"])


def retirement_inventory(conn, project):
    """Versioned retirement scope without identities or credential material."""
    resources = conn.execute(
        """SELECT resource_id::text,name,provider,state,version
        FROM store_resources WHERE owner_project=%s AND state<>'purged' ORDER BY resource_id""",
        (project,),
    ).fetchall()
    grants = conn.execute(
        """SELECT g.grant_id::text,g.resource_id::text,g.kind,g.mode,g.state,g.version,
        g.consumer_project,g.component FROM store_grants g JOIN store_resources r USING(resource_id)
        WHERE (r.owner_project=%s OR g.consumer_project=%s) AND g.state IN ('pending','active')
        ORDER BY g.grant_id""",
        (project, project),
    ).fetchall()
    return {
        "named_store_resources": [
            dict(zip(("resource_id", "name", "provider", "state", "version"), row))
            for row in resources
        ],
        "named_store_grants": [
            dict(
                zip(
                    (
                        "grant_id",
                        "resource_id",
                        "kind",
                        "mode",
                        "state",
                        "version",
                        "consumer_project",
                        "component",
                    ),
                    row,
                )
            )
            for row in grants
        ],
    }


def retire_project(conn, project):
    # Persist admission/access denial as soon as retirement starts, even while
    # the namespace is terminating and projects.status is still applied.
    conn.execute(
        "INSERT INTO store_project_retirements(project) VALUES(%s) ON CONFLICT DO NOTHING",
        (project,),
    )
    conn.execute(
        """UPDATE store_resources SET state='retired',observed_state='pending',version=version+1,
        updated_at=now() WHERE owner_project=%s AND state='active'""",
        (project,),
    )
    conn.execute(
        """UPDATE store_grants SET state='revoked',observed_state='pending',version=version+1,updated_at=now()
        WHERE state IN ('pending','active') AND (consumer_project=%s OR resource_id IN
            (SELECT resource_id FROM store_resources WHERE owner_project=%s))""",
        (project, project),
    )


def authorized_key(conn, fingerprint, relay_ip):
    import ipaddress

    from ..human_database_access import FINGERPRINT_PATTERN

    relay_ip = str(ipaddress.ip_address(relay_ip))
    if not FINGERPRINT_PATTERN.fullmatch(fingerprint):
        return None
    rows = conn.execute(
        """SELECT k.public_key,k.issuer,k.subject,c.relay_port,r.owner_project
        FROM store_human_keys k JOIN store_grants g ON g.issuer=k.issuer AND g.subject=k.subject
        JOIN store_resources r USING(resource_id) JOIN store_credentials c USING(grant_id)
        JOIN projects p ON p.name=r.owner_project WHERE k.fingerprint=%s AND g.kind='human'
            AND g.state='active' AND r.state='active' AND r.observed_state='active' AND p.status<>'retired'
            AND c.state='active' AND c.grant_version=g.version AND c.expires_at>now()
            AND NOT EXISTS(SELECT 1 FROM store_project_retirements retired WHERE retired.project=r.owner_project)
            AND c.relay_port IS NOT NULL ORDER BY c.relay_port LIMIT 65""",
        (fingerprint,),
    ).fetchall()
    if not rows or len(rows) > 64:
        return None
    permissions = ",".join(f'permitopen="{relay_ip}:{row[3]}"' for row in rows)
    return (
        f"restrict,port-forwarding,{permissions} {rows[0][0]}",
        rows[0][4],
        rows[0][1],
        rows[0][2],
    )
