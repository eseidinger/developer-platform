"""A narrow, read-only view for workload telemetry admission."""

import json
import os

import psycopg
from psycopg import sql


def initialize(conn):
    password = os.environ.get("TELEMETRY_CATALOG_PASSWORD", "")
    if len(password) < 32:
        raise RuntimeError(
            "TELEMETRY_CATALOG_PASSWORD must contain at least 32 characters"
        )
    conn.execute("""CREATE OR REPLACE VIEW telemetry_component_opt_ins AS
        SELECT p.name AS project, c.item->>'name' AS component
        FROM projects p
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(p.spec->'components', '[]'::jsonb)) AS c(item)
        WHERE p.status = 'applied' AND c.item->'tracing'->>'enabled' = 'true'""")
    conn.execute("""CREATE OR REPLACE VIEW telemetry_project_partitions AS
        SELECT p.name AS project,p.project_id FROM projects p
        WHERE p.status='applied' AND NOT EXISTS(SELECT 1 FROM project_lifecycle_operations l
        WHERE l.project_id=p.project_id AND l.state IN ('queued','running','blocked'))""")
    conn.execute(
        "CREATE OR REPLACE VIEW telemetry_project_identities AS SELECT name AS project,project_id FROM projects"
    )
    if not conn.execute(
        "SELECT 1 FROM pg_roles WHERE rolname='telemetry_catalog'"
    ).fetchone():
        conn.execute(
            "CREATE ROLE telemetry_catalog LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
        )
    conn.execute(
        sql.SQL("ALTER ROLE telemetry_catalog PASSWORD {}").format(
            sql.Literal(password)
        )
    )
    conn.execute("GRANT CONNECT ON DATABASE platform TO telemetry_catalog")
    conn.execute("REVOKE ALL ON telemetry_component_opt_ins FROM PUBLIC")
    conn.execute(
        "GRANT SELECT ON telemetry_component_opt_ins,telemetry_project_partitions,telemetry_project_identities TO telemetry_catalog"
    )
    conn.execute(
        "REVOKE ALL ON telemetry_project_partitions,telemetry_project_identities FROM PUBLIC"
    )


def grafana_projects():
    """Return catalog identities for operator data-source reconciliation."""
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname="platform",
        user="telemetry_catalog",
        password=os.environ["TELEMETRY_CATALOG_PASSWORD"],
        connect_timeout=3,
    ) as conn:
        return conn.execute(
            "SELECT project, project_id::text "
            "FROM telemetry_project_identities ORDER BY project"
        ).fetchall()


if __name__ == "__main__":
    print(json.dumps(grafana_projects()))
