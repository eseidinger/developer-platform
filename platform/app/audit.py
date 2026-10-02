"""Append-only, secret-redacted audit records for the platform API."""
from dataclasses import dataclass
import os
import re
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb


AUDIT_OWNER = "platform_audit_owner"
AUDIT_WRITER = "platform_audit_writer"
AUDIT_READER = "platform_audit_reader"
REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(r"(?:password|secret|token|authorization|credential|cookie|key)$", re.IGNORECASE)
BEARER_VALUE = re.compile(r"(?i)\b(bearer|basic)\s+[^\s,;]+")
KEY_VALUE = re.compile(
    r"(?i)\b(password|secret|token|authorization|credential|cookie|api[_-]?key)\s*[:=]\s*[^,\s]+"
)


@dataclass(frozen=True)
class Actor:
    """A stable, non-secret representation of the caller for an audit event."""

    kind: str
    identifier: str | None


def redact(value: Any, key: str | None = None) -> Any:
    """Return JSON-safe data without credential values or bearer material."""
    if key and SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = BEARER_VALUE.sub(r"\1 " + REDACTED, value)
        return KEY_VALUE.sub(lambda match: match.group(1) + "=" + REDACTED, value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def audit_connect():
    """Connect using the role that can append events but cannot alter or read them."""
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname="platform",
        user=AUDIT_WRITER,
        password=os.environ["PLATFORM_AUDIT_PASSWORD"],
        connect_timeout=5,
        autocommit=True,
    )


def audit_reader_connect():
    """Connect with the role limited to reading redacted audit events."""
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"], dbname="platform", user=AUDIT_READER,
        password=os.environ["PLATFORM_AUDIT_READER_PASSWORD"], connect_timeout=5, autocommit=True,
    )


def initialize(conn) -> None:
    """Create the audit boundary from the privileged bootstrap connection."""
    for role in (AUDIT_OWNER, AUDIT_WRITER, AUDIT_READER):
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                 "NOREPLICATION NOBYPASSRLS").format(sql.Identifier(role)))
    conn.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                         "NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4 PASSWORD {}")
                 .format(sql.Identifier(AUDIT_WRITER), sql.Literal(os.environ["PLATFORM_AUDIT_PASSWORD"])))
    conn.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                         "NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4 PASSWORD {}")
                 .format(sql.Identifier(AUDIT_READER), sql.Literal(os.environ["PLATFORM_AUDIT_READER_PASSWORD"])))
    conn.execute("CREATE SCHEMA IF NOT EXISTS platform_audit")
    conn.execute(sql.SQL("ALTER SCHEMA platform_audit OWNER TO {}").format(sql.Identifier(AUDIT_OWNER)))
    conn.execute("""CREATE TABLE IF NOT EXISTS platform_audit.events (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        actor_kind TEXT NOT NULL,
        actor_id TEXT,
        action TEXT NOT NULL,
        target_kind TEXT NOT NULL,
        target_id TEXT,
        scope JSONB NOT NULL DEFAULT '{}'::jsonb,
        result TEXT NOT NULL CHECK (result IN ('succeeded', 'failed', 'denied', 'rejected')),
        revision TEXT,
        operation_id TEXT,
        detail JSONB NOT NULL DEFAULT '{}'::jsonb
    )""")
    conn.execute(sql.SQL("ALTER TABLE platform_audit.events OWNER TO {}").format(sql.Identifier(AUDIT_OWNER)))
    conn.execute("ALTER TABLE platform_audit.events ENABLE ROW LEVEL SECURITY")
    conn.execute("ALTER TABLE platform_audit.events FORCE ROW LEVEL SECURITY")
    conn.execute("DROP POLICY IF EXISTS audit_owner_append ON platform_audit.events")
    conn.execute(sql.SQL("CREATE POLICY audit_owner_append ON platform_audit.events FOR INSERT TO {} "
                         "WITH CHECK (true)").format(sql.Identifier(AUDIT_OWNER)))
    conn.execute("DROP POLICY IF EXISTS audit_reader_select ON platform_audit.events")
    conn.execute(sql.SQL("CREATE POLICY audit_reader_select ON platform_audit.events FOR SELECT TO {} "
                         "USING (true)").format(sql.Identifier(AUDIT_READER)))
    conn.execute("""CREATE OR REPLACE FUNCTION platform_audit.reject_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'platform audit records are append-only';
        END;
        $$""")
    conn.execute("DROP TRIGGER IF EXISTS events_append_only ON platform_audit.events")
    conn.execute("""CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE
        ON platform_audit.events FOR EACH STATEMENT EXECUTE FUNCTION platform_audit.reject_change()""")
    conn.execute("""CREATE OR REPLACE FUNCTION platform_audit.append_event(
        p_actor_kind TEXT, p_actor_id TEXT, p_action TEXT, p_target_kind TEXT,
        p_target_id TEXT, p_scope JSONB, p_result TEXT, p_revision TEXT,
        p_operation_id TEXT, p_detail JSONB)
        RETURNS BIGINT LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, platform_audit AS $$
        DECLARE event_id BIGINT;
        BEGIN
            INSERT INTO events(actor_kind, actor_id, action, target_kind, target_id,
                               scope, result, revision, operation_id, detail)
            VALUES (p_actor_kind, p_actor_id, p_action, p_target_kind, p_target_id,
                    p_scope, p_result, p_revision, p_operation_id, p_detail)
            RETURNING id INTO event_id;
            RETURN event_id;
        END;
        $$""")
    conn.execute(sql.SQL("ALTER FUNCTION platform_audit.reject_change() OWNER TO {}")
                 .format(sql.Identifier(AUDIT_OWNER)))
    conn.execute(sql.SQL("ALTER FUNCTION platform_audit.append_event(TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, "
                         "TEXT, TEXT, TEXT, JSONB) OWNER TO {}").format(sql.Identifier(AUDIT_OWNER)))
    conn.execute("REVOKE ALL ON DATABASE platform FROM PUBLIC")
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE platform TO {}").format(sql.Identifier(AUDIT_WRITER)))
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE platform TO {}").format(sql.Identifier(AUDIT_READER)))
    conn.execute("REVOKE ALL ON SCHEMA platform_audit FROM PUBLIC")
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA platform_audit TO {}").format(sql.Identifier(AUDIT_WRITER)))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA platform_audit TO {}").format(sql.Identifier(AUDIT_READER)))
    conn.execute("REVOKE ALL ON TABLE platform_audit.events FROM PUBLIC")
    conn.execute(sql.SQL("GRANT SELECT ON TABLE platform_audit.events TO {}").format(sql.Identifier(AUDIT_READER)))
    conn.execute("REVOKE ALL ON FUNCTION platform_audit.reject_change() FROM PUBLIC")
    conn.execute("REVOKE ALL ON FUNCTION platform_audit.append_event(TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, "
                 "TEXT, TEXT, TEXT, JSONB) FROM PUBLIC")
    conn.execute(sql.SQL("GRANT EXECUTE ON FUNCTION platform_audit.append_event(TEXT, TEXT, TEXT, TEXT, TEXT, "
                         "JSONB, TEXT, TEXT, TEXT, JSONB) TO {}").format(sql.Identifier(AUDIT_WRITER)))


def record_event(actor: Actor, action: str, target_kind: str, target_id: str | None, result: str,
                 scope: dict[str, Any] | None = None, detail: dict[str, Any] | None = None,
                 revision: str | None = None, operation_id: str | None = None) -> int:
    """Durably append one event through the limited audit-writer role."""
    with audit_connect() as conn:
        row = conn.execute("""SELECT platform_audit.append_event(
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", (
            actor.kind, actor.identifier, action, target_kind, target_id,
            Jsonb(redact(scope or {})), result, revision, operation_id, Jsonb(redact(detail or {})),
        )).fetchone()
    return row[0]
