"""A narrow, read-only view for workload telemetry admission."""

import os
from psycopg import sql


def initialize(conn):
    password = os.environ.get("TELEMETRY_CATALOG_PASSWORD", "")
    if len(password) < 32:
        raise RuntimeError("TELEMETRY_CATALOG_PASSWORD must contain at least 32 characters")
    conn.execute("""CREATE OR REPLACE VIEW telemetry_component_opt_ins AS
        SELECT p.name AS project, c.item->>'name' AS component
        FROM projects p
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(p.spec->'components', '[]'::jsonb)) AS c(item)
        WHERE p.status = 'applied' AND c.item->'tracing'->>'enabled' = 'true'""")
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='telemetry_catalog'").fetchone():
        conn.execute("CREATE ROLE telemetry_catalog LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
    conn.execute(sql.SQL("ALTER ROLE telemetry_catalog PASSWORD {}").format(sql.Literal(password)))
    conn.execute("GRANT CONNECT ON DATABASE platform TO telemetry_catalog")
    conn.execute("REVOKE ALL ON telemetry_component_opt_ins FROM PUBLIC")
    conn.execute("GRANT SELECT ON telemetry_component_opt_ins TO telemetry_catalog")
