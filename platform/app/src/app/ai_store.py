"""Durable, project-scoped AI status and data-classification policy."""

from uuid import uuid4
from psycopg.types.json import Jsonb

CLASSES = {"public", "internal", "confidential", "restricted"}


def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_project_policies (
        project TEXT PRIMARY KEY REFERENCES projects(name) ON DELETE RESTRICT,
        classification TEXT NOT NULL CHECK (classification IN ('public','internal','confidential','restricted')),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_runs (
        run_id UUID PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(name),
        requester_issuer TEXT NOT NULL, requester_subject TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('explain_application','investigate_incident','development_assistance')),
        state TEXT NOT NULL CHECK (state IN ('running','completed','abstained','failed')),
        model TEXT, result JSONB, evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        tool_calls INTEGER NOT NULL DEFAULT 0, estimated_cost_usd NUMERIC(8,6) NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ)""")
    conn.execute("ALTER TABLE ai_runs ADD COLUMN IF NOT EXISTS base_revision BIGINT")
    conn.execute("ALTER TABLE ai_runs ALTER COLUMN estimated_cost_usd DROP NOT NULL")
    conn.execute("ALTER TABLE ai_runs ALTER COLUMN estimated_cost_usd DROP DEFAULT")
    conn.execute("CREATE INDEX IF NOT EXISTS ai_runs_history_idx ON ai_runs(project,created_at DESC,run_id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS ai_runs_project_created_idx ON ai_runs(project,created_at DESC)")
    conn.execute("ALTER TABLE ai_runs DROP CONSTRAINT IF EXISTS ai_runs_kind_check")
    conn.execute("""ALTER TABLE ai_runs ADD CONSTRAINT ai_runs_kind_check
        CHECK (kind IN ('explain_application','investigate_incident','development_assistance'))""")


def set_policy(conn, project: str, classification: str):
    if classification not in CLASSES:
        raise ValueError("Invalid AI data classification")
    return conn.execute("""INSERT INTO ai_project_policies(project,classification) VALUES (%s,%s)
        ON CONFLICT(project) DO UPDATE SET classification=excluded.classification,updated_at=now()
        RETURNING classification""", (project, classification)).fetchone()


def classification(conn, project: str) -> str | None:
    row = conn.execute("SELECT classification FROM ai_project_policies WHERE project=%s", (project,)).fetchone()
    return row[0] if row else None


def create_run(conn, project, principal, kind, model, base_revision=None):
    run_id = uuid4()
    conn.execute("""INSERT INTO ai_runs(run_id,project,requester_issuer,requester_subject,kind,state,model,base_revision)
        VALUES (%s,%s,%s,%s,%s,'running',%s,%s)""",
        (run_id, project, principal.issuer, principal.subject, kind, model, base_revision))
    return run_id


def finish_run(conn, run_id, state, result, evidence, tool_calls, estimated_cost):
    conn.execute("""UPDATE ai_runs SET state=%s,result=%s,evidence=%s,tool_calls=%s,
        estimated_cost_usd=%s,completed_at=now() WHERE run_id=%s AND state='running'""",
        (state, Jsonb(result), Jsonb(evidence), tool_calls, estimated_cost, run_id))


def get_run(conn, project, run_id):
    return conn.execute("""SELECT run_id,kind,state,model,result,evidence,tool_calls,
        estimated_cost_usd,created_at,completed_at,base_revision FROM ai_runs
        WHERE project=%s AND run_id=%s""", (project, run_id)).fetchone()


def history(conn, project, limit, before=None):
    """Keyset pagination; a foreign/missing cursor cannot reveal another project."""
    return conn.execute("""SELECT run_id,kind,state,model,tool_calls,estimated_cost_usd,
        created_at,completed_at,base_revision FROM ai_runs
        WHERE project=%s AND (%s::uuid IS NULL OR (created_at,run_id)<(
            SELECT created_at,run_id FROM ai_runs WHERE project=%s AND run_id=%s))
        ORDER BY created_at DESC,run_id DESC LIMIT %s""",
        (project, before, project, before, limit + 1)).fetchall()
