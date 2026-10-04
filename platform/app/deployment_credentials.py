"""Durable metadata and authorization state for automation credentials."""
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from .audit import Actor
from .identity import Principal


def initialize(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS deployment_credentials (
        credential_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'deployment'
            CHECK (kind IN ('deployment', 'test-runner', 'test-persona')),
        project TEXT REFERENCES projects(name) ON DELETE RESTRICT,
        environment TEXT NOT NULL DEFAULT 'default' CHECK (environment = 'default'),
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        provider_client_id TEXT NOT NULL UNIQUE,
        provider_resource_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL CHECK (status IN ('active', 'revocation_pending', 'revoked')),
        created_by_issuer TEXT NOT NULL,
        created_by_subject TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at TIMESTAMPTZ NOT NULL,
        last_used_at TIMESTAMPTZ,
        rotated_from UUID REFERENCES deployment_credentials(credential_id) ON DELETE RESTRICT,
        test_run_id TEXT,
        revoked_at TIMESTAMPTZ,
        UNIQUE(project, name),
        UNIQUE(issuer, subject)
    )""")
    conn.execute("ALTER TABLE deployment_credentials ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'deployment'")
    conn.execute("ALTER TABLE deployment_credentials ADD COLUMN IF NOT EXISTS test_run_id TEXT")
    conn.execute("ALTER TABLE deployment_credentials ALTER COLUMN project DROP NOT NULL")
    conn.execute("""DO $$ BEGIN
        ALTER TABLE deployment_credentials ADD CONSTRAINT deployment_credentials_kind_check
            CHECK (kind IN ('deployment', 'test-runner', 'test-persona'));
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""")
    conn.execute("CREATE INDEX IF NOT EXISTS deployment_credentials_scope_idx "
                 "ON deployment_credentials(project, status, expires_at)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS deployment_credentials_platform_name_idx "
                 "ON deployment_credentials(kind, name) WHERE project IS NULL AND status <> 'revoked'")
    conn.execute("REVOKE ALL ON TABLE deployment_credentials FROM PUBLIC")


@dataclass(frozen=True)
class CredentialAccess:
    credential_id: UUID
    kind: str
    project: str | None
    active: bool


def access_scope(conn, principal: Principal) -> CredentialAccess | None:
    """Return current automation-credential state, or None for a human principal."""
    row = conn.execute("""SELECT credential_id, kind, project, status='active' AND expires_at>now()
        FROM deployment_credentials WHERE issuer=%s AND subject=%s""",
                       (principal.issuer, principal.subject)).fetchone()
    return None if row is None else CredentialAccess(row[0], row[1], row[2], bool(row[3]))


def record_use(conn, principal: Principal) -> None:
    conn.execute("""UPDATE deployment_credentials SET last_used_at=now()
        WHERE issuer=%s AND subject=%s AND status='active' AND expires_at>now()""",
                 (principal.issuer, principal.subject))


def reconcile_pending_cleanup(connect: Callable, delete_client: Callable, audit: Callable, log) -> int:
    """Retry fail-closed provider deletion; missing provider clients count as success."""
    with connect() as conn:
        rows = conn.execute("""SELECT credential_id, provider_resource_id, kind, project
            FROM deployment_credentials WHERE status='revocation_pending'
            ORDER BY created_at LIMIT 25""").fetchall()
    completed = 0
    for credential_id, provider_resource_id, kind, project in rows:
        try:
            delete_client(provider_resource_id)
        except Exception as exc:
            log.warning("Automation credential cleanup deferred credential_id=%s error_type=%s",
                        credential_id, type(exc).__name__)
            continue
        with connect() as conn:
            updated = conn.execute("""UPDATE deployment_credentials
                SET status='revoked', revoked_at=COALESCE(revoked_at, now())
                WHERE credential_id=%s AND status='revocation_pending'""", (credential_id,)).rowcount
        if updated:
            completed += 1
            audit(Actor("system", "credential-cleanup"), "automation-credential.cleanup",
                  "automation-credential", str(credential_id), "succeeded",
                  {"project": project} if project else {"scope": "platform"}, {"kind": kind})
    return completed


def cleanup_loop(stop, connect: Callable, delete_client: Callable, audit: Callable, log,
                 interval: float = 30) -> None:
    while not stop.is_set():
        try:
            reconcile_pending_cleanup(connect, delete_client, audit, log)
        except Exception as exc:
            log.error("Automation credential cleanup iteration failed error_type=%s", type(exc).__name__)
        stop.wait(interval)


def public_record(row: tuple[Any, ...]) -> dict[str, Any]:
    return {"credential_id": str(row[0]), "name": row[1], "kind": row[2], "project": row[3],
            "environment": row[4], "status": "expired" if row[5] == "active" and row[8] else row[5],
            "created_at": row[6].isoformat(), "expires_at": row[7].isoformat(),
            "last_used_at": row[9].isoformat() if row[9] else None,
            "rotated_from": str(row[10]) if row[10] else None, "test_run_id": row[11]}
