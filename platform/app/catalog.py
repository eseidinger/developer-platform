"""Stable catalog identities and immutable desired-application revisions."""
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb


DEFAULT_ENVIRONMENT = "default"


def initialize(conn) -> None:
    with conn.transaction():
        conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS project_id UUID")
        conn.execute("UPDATE projects SET project_id=gen_random_uuid() WHERE project_id IS NULL")
        conn.execute("ALTER TABLE projects ALTER COLUMN project_id SET DEFAULT gen_random_uuid()")
        conn.execute("ALTER TABLE projects ALTER COLUMN project_id SET NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS projects_project_id_idx ON projects(project_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS project_environments (
            environment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE RESTRICT,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(project_id, name)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS project_applications (
            application_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            environment_id UUID NOT NULL REFERENCES project_environments(environment_id) ON DELETE RESTRICT,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(environment_id, name)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_revisions (
            application_id UUID NOT NULL REFERENCES project_applications(application_id) ON DELETE RESTRICT,
            revision BIGINT NOT NULL CHECK (revision > 0),
            spec JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY(application_id, revision)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_operations (
            operation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            application_id UUID NOT NULL,
            revision BIGINT NOT NULL,
            operation_kind TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed')),
            actor_issuer TEXT NOT NULL,
            actor_subject TEXT NOT NULL,
            envelope_version SMALLINT NOT NULL CHECK (envelope_version > 0),
            envelope JSONB NOT NULL,
            result_version SMALLINT CHECK (result_version > 0),
            result JSONB,
            error_code TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            FOREIGN KEY(application_id, revision)
                REFERENCES application_revisions(application_id, revision) ON DELETE RESTRICT
        )""")
        conn.execute("ALTER TABLE application_operations ADD COLUMN IF NOT EXISTS actor_issuer TEXT")
        conn.execute("ALTER TABLE application_operations ADD COLUMN IF NOT EXISTS actor_subject TEXT")
        conn.execute("""UPDATE application_operations
            SET actor_issuer=COALESCE(actor_issuer, ''), actor_subject=COALESCE(actor_subject, '')
            WHERE actor_issuer IS NULL OR actor_subject IS NULL""")
        conn.execute("ALTER TABLE application_operations ALTER COLUMN actor_issuer SET NOT NULL")
        conn.execute("ALTER TABLE application_operations ALTER COLUMN actor_subject SET NOT NULL")
        conn.execute("""CREATE INDEX IF NOT EXISTS application_operations_pending_idx
            ON application_operations(state, created_at)
            WHERE state IN ('queued', 'running')""")
        conn.execute("""INSERT INTO project_environments(project_id, name)
            SELECT project_id, %s FROM projects
            ON CONFLICT(project_id, name) DO NOTHING""", (DEFAULT_ENVIRONMENT,))
        conn.execute("""INSERT INTO project_applications(environment_id, name)
            SELECT e.environment_id, p.name
            FROM project_environments e
            JOIN projects p ON p.project_id=e.project_id
            WHERE e.name=%s
            ON CONFLICT(environment_id, name) DO NOTHING""", (DEFAULT_ENVIRONMENT,))
        conn.execute("""INSERT INTO application_revisions(application_id, revision, spec)
            SELECT a.application_id, 1, p.spec
            FROM project_applications a
            JOIN project_environments e ON e.environment_id=a.environment_id
            JOIN projects p ON p.project_id=e.project_id AND p.name=a.name
            ON CONFLICT(application_id, revision) DO NOTHING""")


def ensure_default_application(conn, project_id: UUID, name: str,
                               spec: dict[str, Any]) -> tuple[UUID, int]:
    environment = conn.execute("""INSERT INTO project_environments(project_id, name)
        VALUES (%s, %s)
        ON CONFLICT(project_id, name) DO UPDATE SET name=excluded.name
        RETURNING environment_id""", (project_id, DEFAULT_ENVIRONMENT)).fetchone()
    if environment is None:
        raise RuntimeError("Could not resolve the default environment")

    application = conn.execute("""INSERT INTO project_applications(environment_id, name)
        VALUES (%s, %s)
        ON CONFLICT(environment_id, name) DO UPDATE SET name=excluded.name
        RETURNING application_id""", (environment[0], name)).fetchone()
    if application is None:
        raise RuntimeError("Could not resolve the default application")

    latest = conn.execute("""SELECT revision, spec FROM application_revisions
        WHERE application_id=%s ORDER BY revision DESC LIMIT 1""", (application[0],)).fetchone()
    if latest is not None and latest[1] == spec:
        return application[0], latest[0]

    revision = 1 if latest is None else latest[0] + 1
    conn.execute("""INSERT INTO application_revisions(application_id, revision, spec)
        VALUES (%s, %s, %s)""", (application[0], revision, Jsonb(spec)))
    return application[0], revision
