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
        with self.connection(name) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION {}").format(sql.Identifier(owner)))
            conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            conn.execute("CREATE SCHEMA IF NOT EXISTS platform_control AUTHORIZATION postgres")
            conn.execute("REVOKE ALL ON SCHEMA platform_control FROM PUBLIC")
            conn.execute("""CREATE OR REPLACE FUNCTION platform_control.guard_extensions() RETURNS event_trigger
                LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
                BEGIN
                    IF session_user <> 'postgres' THEN
                        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Extensions are managed by the platform';
                    END IF;
                END $$""")
            if not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtname='platform_store_extensions'").fetchone():
                conn.execute("""CREATE EVENT TRIGGER platform_store_extensions ON ddl_command_start
                    WHEN TAG IN ('CREATE EXTENSION','ALTER EXTENSION','DROP EXTENSION')
                    EXECUTE FUNCTION platform_control.guard_extensions()""")
            conn.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(owner)))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(reader)))
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
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} VALID UNTIL {} CONNECTION LIMIT 20")
                .format(sql.Identifier(role), sql.Literal(catalog.secret_for(credential["credential_id"])),
                        sql.Literal(credential["expires_at"])))
            conn.execute(sql.SQL("GRANT {} TO {} WITH ADMIN FALSE")
                .format(sql.Identifier(group), sql.Identifier(role)))
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
