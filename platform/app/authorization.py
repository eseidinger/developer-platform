"""Platform-owned principal and project-grant storage."""
from dataclasses import dataclass
import os
from typing import Iterable

from psycopg.types.json import Jsonb

from .identity import Principal


ROLE_ORDER = {"viewer": 1, "developer": 2, "project-admin": 3, "platform-admin": 4}
PERMISSIONS = {
    "view": {"viewer", "developer", "project-admin", "platform-admin"},
    "change": {"developer", "project-admin", "platform-admin"},
    "retire": {"project-admin", "platform-admin"},
    "grant": {"project-admin", "platform-admin"},
}


@dataclass(frozen=True)
class Grant:
    issuer: str
    subject: str
    role: str
    scope_kind: str
    scope_id: str | None


def initialize(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS platform_principals (
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        display_name TEXT,
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (issuer, subject)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS platform_grants (
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        scope_kind TEXT NOT NULL CHECK (scope_kind IN ('platform', 'project')),
        scope_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('viewer', 'developer', 'project-admin', 'platform-admin')),
        granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (issuer, subject, scope_kind, scope_id),
        FOREIGN KEY (issuer, subject) REFERENCES platform_principals(issuer, subject) ON DELETE RESTRICT,
        CHECK ((scope_kind = 'platform' AND scope_id = '*' AND role = 'platform-admin')
            OR (scope_kind = 'project' AND scope_id IS NOT NULL AND role <> 'platform-admin'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS platform_grants_scope_idx "
                 "ON platform_grants(scope_kind, scope_id, issuer, subject)")
    conn.execute("""CREATE TABLE IF NOT EXISTS platform_authorization_metadata (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    conn.execute("REVOKE ALL ON TABLE platform_principals, platform_grants, platform_authorization_metadata FROM PUBLIC")


def upsert_principal(conn, principal: Principal) -> None:
    conn.execute("""INSERT INTO platform_principals(issuer, subject, display_name)
        VALUES (%s, %s, %s)
        ON CONFLICT(issuer, subject) DO UPDATE SET display_name=excluded.display_name, last_seen_at=now()""",
                 (principal.issuer, principal.subject, principal.display_name))


def _roles(conn, principal: Principal, project: str | None = None) -> set[str]:
    rows = conn.execute("""SELECT role FROM platform_grants
        WHERE issuer=%s AND subject=%s AND (scope_kind='platform' OR (scope_kind='project' AND scope_id=%s))""",
                        (principal.issuer, principal.subject, project)).fetchall()
    return {row[0] for row in rows}


def is_allowed(conn, principal: Principal, permission: str, project: str | None = None) -> bool:
    return bool(_roles(conn, principal, project) & PERMISSIONS[permission])


def is_platform_admin(conn, principal: Principal) -> bool:
    return "platform-admin" in _roles(conn, principal)


def projects_for_principal(conn, principal: Principal):
    if is_platform_admin(conn, principal):
        return conn.execute("SELECT name, spec, status FROM projects ORDER BY name").fetchall()
    return conn.execute("""SELECT p.name, p.spec, p.status FROM projects p
        JOIN platform_grants g ON g.scope_kind='project' AND g.scope_id=p.name
        WHERE g.issuer=%s AND g.subject=%s ORDER BY p.name""", (principal.issuer, principal.subject)).fetchall()


def grants_for_project(conn, project: str):
    """Return platform-owned project grants for restricted operator inspection."""
    return conn.execute("""SELECT g.issuer, g.subject, p.display_name, g.role, g.granted_at
        FROM platform_grants g
        JOIN platform_principals p ON p.issuer=g.issuer AND p.subject=g.subject
        WHERE g.scope_kind='project' AND g.scope_id=%s
        ORDER BY g.granted_at, g.issuer, g.subject""", (project,)).fetchall()


def grant(conn, principal: Principal, scope_kind: str, scope_id: str | None, role: str) -> None:
    if role not in ROLE_ORDER or scope_kind not in {"platform", "project"}:
        raise ValueError("Unsupported role or scope")
    if scope_kind == "platform" and (scope_id not in (None, "*") or role != "platform-admin"):
        raise ValueError("Platform scope requires platform-admin")
    if scope_kind == "project" and (not scope_id or role == "platform-admin"):
        raise ValueError("Project scope requires a project role")
    upsert_principal(conn, principal)
    conn.execute("""INSERT INTO platform_grants(issuer, subject, scope_kind, scope_id, role)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(issuer, subject, scope_kind, scope_id) DO UPDATE SET role=excluded.role, granted_at=now()""",
                 (principal.issuer, principal.subject, scope_kind, "*" if scope_kind == "platform" else scope_id, role))


def revoke(conn, issuer: str, subject: str, scope_kind: str, scope_id: str | None) -> bool:
    return conn.execute("""DELETE FROM platform_grants
        WHERE issuer=%s AND subject=%s AND scope_kind=%s AND scope_id=%s""",
                        (issuer, subject, scope_kind, "*" if scope_kind == "platform" else scope_id)).rowcount == 1


def bootstrap_platform_admin(conn, issuer: str) -> Principal | None:
    row = conn.execute("SELECT value FROM platform_authorization_metadata WHERE key='bootstrap_grant'").fetchone()
    if row:
        return None
    subject = os.environ.get("PLATFORM_BOOTSTRAP_SUBJECT", "")
    if not subject:
        raise RuntimeError("PLATFORM_BOOTSTRAP_SUBJECT is required until the first platform-admin grant exists")
    principal = Principal(issuer, subject, "bootstrap platform administrator")
    grant(conn, principal, "platform", None, "platform-admin")
    conn.execute("""INSERT INTO platform_authorization_metadata(key, value)
        VALUES ('bootstrap_grant', %s)""", (Jsonb({"issuer": issuer, "subject": subject}),))
    return principal
