"""Shared PostgreSQL; one independent database, schema owner and reader role per resource."""
import os
from contextlib import contextmanager
import psycopg
from psycopg import sql
from . import catalog


class Postgres:
    quota_enforcement = "advisory: PostgreSQL has no hard per-database byte quota"

    def __init__(self, connection=None):
        self.connection = connection or self._connect

    @staticmethod
    def _connect(database):
        return psycopg.connect(host=os.environ["POSTGRES_HOST"], dbname=database,
            user="postgres", password=os.environ["POSTGRES_PASSWORD"], connect_timeout=3,
            autocommit=True, options="-c statement_timeout=5000 -c lock_timeout=2000")

    def endpoint(self):
        import ipaddress
        return str(ipaddress.ip_address(os.environ["POSTGRES_IP"])), 5432

    def provision(self, resource):
        name = catalog.identifier(resource["resource_id"])
        owner, reader = name + "_owner", name + "_reader"
        with self.connection("postgres") as conn:
            for role in (owner, reader):
                if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
                        .format(sql.Identifier(role)))
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                # Database owned by operator, NOT writer. Writer may create schemas
                # but cannot drop the named resource or bypass the purge workflow.
                conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
            conn.execute(sql.SQL("GRANT CONNECT,CREATE,TEMPORARY ON DATABASE {} TO {}")
                .format(sql.Identifier(name), sql.Identifier(owner)))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
                .format(sql.Identifier(name), sql.Identifier(reader)))
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='platform_monitor'").fetchone():
                conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO platform_monitor").format(sql.Identifier(name)))
        with self.connection(name) as conn, conn.transaction():
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION {}").format(sql.Identifier(owner)))
            conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            conn.execute("CREATE SCHEMA IF NOT EXISTS platform_control AUTHORIZATION postgres")
            conn.execute("REVOKE ALL ON SCHEMA platform_control FROM PUBLIC")
            conn.execute("""CREATE OR REPLACE FUNCTION platform_control.guard_extensions() RETURNS event_trigger
                LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
                BEGIN
                    IF session_user <> 'postgres' THEN
                        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Extensions and access permissions are managed by the platform';
                    END IF;
                END $$""")
            conn.execute("DROP EVENT TRIGGER IF EXISTS platform_store_extensions")
            conn.execute("""CREATE EVENT TRIGGER platform_store_extensions ON ddl_command_start
                WHEN TAG IN ('CREATE EXTENSION','ALTER EXTENSION','DROP EXTENSION','GRANT','REVOKE','ALTER DEFAULT PRIVILEGES')
                EXECUTE FUNCTION platform_control.guard_extensions()""")
            conn.execute("""CREATE OR REPLACE FUNCTION platform_control.guard_definer() RETURNS event_trigger
                LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
                BEGIN
                    IF session_user <> 'postgres' AND EXISTS(
                        SELECT 1 FROM pg_catalog.pg_event_trigger_ddl_commands() d
                        JOIN pg_catalog.pg_proc p ON d.classid='pg_catalog.pg_proc'::regclass AND p.oid=d.objid
                        WHERE p.prosecdef) THEN
                        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Security-definer routines are managed by the platform';
                    END IF;
                END $$""")
            if not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtname='platform_store_definer'").fetchone():
                conn.execute("""CREATE EVENT TRIGGER platform_store_definer ON ddl_command_end
                    WHEN TAG IN ('CREATE FUNCTION','ALTER FUNCTION','CREATE PROCEDURE','ALTER PROCEDURE')
                    EXECUTE FUNCTION platform_control.guard_definer()""")
            conn.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(owner)))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(reader)))
            # PostgreSQL otherwise grants PUBLIC execution on new functions.
            # Readers must not accidentally gain writes through a writer's
            # SECURITY DEFINER function; any function grants must be explicit.
            conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} REVOKE EXECUTE ON ROUTINES FROM PUBLIC")
                .format(sql.Identifier(owner)))
            for target in ("TABLES", "SEQUENCES"):
                conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} GRANT SELECT ON " + target + " TO {}")
                    .format(sql.Identifier(owner), sql.Identifier(reader)))
            conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} GRANT USAGE ON SCHEMAS TO {}")
                .format(sql.Identifier(owner), sql.Identifier(reader)))
            for extension in resource["extensions"]:
                if extension not in {"vector", "age"}:
                    raise ValueError("Unapproved PostgreSQL extension")
                if extension == "vector":
                    conn.execute("CREATE SCHEMA IF NOT EXISTS platform_extensions AUTHORIZATION postgres")
                    conn.execute("REVOKE CREATE ON SCHEMA platform_extensions FROM PUBLIC")
                    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA platform_extensions TO {}, {}")
                        .format(sql.Identifier(owner), sql.Identifier(reader)))
                    conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA platform_extensions")
                else:
                    conn.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(extension)))
            if "age" in resource["extensions"]:
                from . import projections
                projections.initialize(conn, owner, reader)
                conn.execute(sql.SQL("GRANT SELECT ON ag_catalog.ag_graph TO {}, {}")
                    .format(sql.Identifier(owner), sql.Identifier(reader)))
                conn.execute(sql.SQL("GRANT USAGE ON SCHEMA ag_catalog TO {}, {}")
                    .format(sql.Identifier(owner), sql.Identifier(reader)))
            for schema in conn.execute("SELECT nspname FROM pg_namespace WHERE nspowner=(SELECT oid FROM pg_roles WHERE rolname=%s)", (owner,)).fetchall():
                conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}")
                    .format(sql.Identifier(schema[0]), sql.Identifier(reader)))
                conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}")
                    .format(sql.Identifier(schema[0]), sql.Identifier(reader)))

    def issue(self, resource, credential):
        name = catalog.identifier(resource["resource_id"])
        role = catalog.login(credential["credential_id"])
        group = name + ("_owner" if credential["mode"] == "read-write" else "_reader")
        with self.connection("postgres") as conn:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
                    .format(sql.Identifier(role)))
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN NOINHERIT PASSWORD {} VALID UNTIL {} CONNECTION LIMIT 20")
                .format(sql.Identifier(role), sql.Literal(catalog.secret_for(credential["credential_id"])),
                        sql.Literal(credential["expires_at"])))
            conn.execute(sql.SQL("GRANT {} TO {} WITH ADMIN FALSE, INHERIT FALSE, SET TRUE")
                .format(sql.Identifier(group), sql.Identifier(role)))
            # CONNECT is checked before the default SET ROLE takes effect.
            # NOINHERIT prevents RESET ROLE from creating objects owned by a
            # credential generation instead of the shared resource writer.
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
                .format(sql.Identifier(name), sql.Identifier(role)))
            conn.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} SET role TO {}")
                .format(sql.Identifier(role), sql.Identifier(name), sql.Literal(group)))
            if resource["extensions"]:
                path = "ag_catalog,public,platform_extensions" if "age" in resource["extensions"] else "public,platform_extensions"
                conn.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO " + path)
                    .format(sql.Identifier(role), sql.Identifier(name)))

    def revoke(self, resource, credential):
        role = catalog.login(credential["credential_id"])
        with self.connection("postgres") as conn:
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                conn.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(role)))
                conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename=%s AND pid<>pg_backend_pid()", (role,))
                name = catalog.identifier(resource["resource_id"])
                if conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}")
                        .format(sql.Identifier(name), sql.Identifier(role)))
                # Revoked role membership must not retain schema authority.
                for (group,) in conn.execute("""SELECT parent.rolname FROM pg_auth_members m
                    JOIN pg_roles parent ON parent.oid=m.roleid JOIN pg_roles member ON member.oid=m.member
                    WHERE member.rolname=%s""", (role,)).fetchall():
                    conn.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(group), sql.Identifier(role)))

    def purge(self, resource):
        name = catalog.identifier(resource["resource_id"])
        with self.connection("postgres") as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            # Keep revoked login tombstones: they carry no permissions and prevent
            # accidental credential resurrection during delayed cleanup/recovery.
            for role in (name + "_reader", name + "_owner"):
                if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

    def credentials(self, resource, credential):
        host, port = self.endpoint()
        return {"PGHOST": host, "PGPORT": str(port), "PGDATABASE": catalog.identifier(resource["resource_id"]),
                "PGUSER": catalog.login(credential["credential_id"]),
                "PGPASSWORD": catalog.secret_for(credential["credential_id"])}

    def usage(self, resource):
        with self.connection("postgres") as conn:
            return conn.execute("SELECT pg_database_size(%s)", (catalog.identifier(resource["resource_id"]),)).fetchone()[0]

    def probe(self, resource, credential):
        host, port = self.endpoint()
        with psycopg.connect(host=host, port=port, dbname=catalog.identifier(resource["resource_id"]),
                user=catalog.login(credential["credential_id"]), password=catalog.secret_for(credential["credential_id"]),
                connect_timeout=2, options="-c statement_timeout=2000", autocommit=True) as conn:
            conn.execute("SELECT 1").fetchone()

    def validate_recovery(self, resource):
        """No empty replacement database; stale AGE graph OIDs keep quarantine closed."""
        name = catalog.identifier(resource["resource_id"])
        with self.connection("postgres") as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                raise ValueError("Restored resource database is missing")
        with self.connection(name) as conn:
            installed = {row[0] for row in conn.execute("SELECT extname FROM pg_extension")}
            if not set(resource["extensions"]).issubset(installed):
                raise ValueError("Restored resource extension is missing")
            if "age" in resource["extensions"]:
                if conn.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE graphid IS DISTINCT FROM namespace::oid LIMIT 1").fetchone():
                    raise ValueError("AGE graph projection requires authoritative rebuild")
                conn.execute("SET search_path=ag_catalog,public,platform_extensions")
                for (graph,) in conn.execute("SELECT name::text FROM ag_catalog.ag_graph").fetchall():
                    conn.execute(sql.SQL("SELECT * FROM ag_catalog.cypher({}, $$ MATCH (n) RETURN count(n) $$) AS (v ag_catalog.agtype)")
                        .format(sql.Literal(graph))).fetchone()

    def rebuild_projections(self, resource):
        if "age" not in resource["extensions"]:
            return {"graphs": 0}
        from . import projections
        name = catalog.identifier(resource["resource_id"])
        with self.connection(name) as conn:
            return projections.rebuild(conn, name + "_owner")
