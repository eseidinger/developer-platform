#!/usr/bin/env python3
"""Disposable real PostgreSQL tests for named resources and cross-writer ownership."""
import json
import asyncio
from unittest.mock import patch
import os
import secrets
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import psycopg
from psycopg import sql
from app.stores import catalog
from app.stores.contract import ResourceCreate, HumanGrant, BindingRequest
from app.stores import worker
from app.stores.relay import Relay
from app.stores.postgres import Postgres


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30).strip()


def main():
    name = "named-postgres-" + uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    os.environ["DATABASE_KEY"] = secrets.token_hex(32)
    try:
        run("docker", "run", "-d", "--name", name, "--memory", "512m", "--cpus", "1",
            "-e", "POSTGRES_PASSWORD=" + password, "-p", "127.0.0.1::5432",
            "--tmpfs", "/var/lib/postgresql:rw,size=256m", "postgres:18.6-trixie")
        port = int(run("docker", "port", name, "5432/tcp").rsplit(":", 1)[1])
        def connect(database):
            return psycopg.connect(host="127.0.0.1", port=port, dbname=database, user="postgres",
                                   password=password, autocommit=True, connect_timeout=2)
        for _ in range(60):
            try:
                with connect("postgres"):
                    break
            except psycopg.OperationalError:
                time.sleep(.25)
        else:
            raise AssertionError("Disposable PostgreSQL did not start")
        provider = Postgres(connect)
        provider.endpoint = lambda: ("127.0.0.1", port)
        with connect("postgres") as conn:
            conn.execute("CREATE TABLE projects(name TEXT PRIMARY KEY,status TEXT)")
            conn.execute("INSERT INTO projects VALUES ('alpha','applied'),('beta','applied')")
            catalog.initialize(conn)
            with conn.transaction():
                catalog.lock(conn)
                alpha = catalog.create_resource(conn, "alpha", ResourceCreate(name="primary", provider="postgresql"))
                beta = catalog.create_resource(conn, "beta", ResourceCreate(name="other", provider="postgresql"))
            for res in (alpha, beta):
                provider.provision(res)
                conn.execute("UPDATE store_resources SET observed_state='active' WHERE resource_id=%s", (res["resource_id"],))
            credentials = []
            for subject, mode in (("writer-a", "read-write"), ("writer-b", "read-write"), ("reader", "read-only")):
                with conn.transaction():
                    grant = catalog.create_human_grant(conn, alpha,
                        HumanGrant(issuer="https://fixture.invalid", subject=subject, mode=mode), "fixture-admin")
                    cred = catalog.issue(conn, grant)
                    credentials.append(cred)
                provider.issue(alpha, cred)
            def login(credential, resource=alpha):
                return psycopg.connect(host="127.0.0.1", port=port,
                    dbname=catalog.identifier(resource["resource_id"]), user=catalog.login(credential["credential_id"]),
                    password=catalog.secret_for(credential["credential_id"]), autocommit=True, connect_timeout=2)
            a, b, reader = credentials
            with login(a) as writer:
                writer.execute("CREATE TABLE public.shared(id INTEGER)")
                writer.execute("INSERT INTO public.shared VALUES(1)")
                writer.execute("CREATE SCHEMA another")
                writer.execute("CREATE TABLE another.future(id INTEGER)")
                writer.execute("INSERT INTO another.future VALUES(2)")
            with login(b) as writer:
                writer.execute("ALTER TABLE public.shared ADD COLUMN note TEXT")
                writer.execute("UPDATE public.shared SET note='changed by second writer'")
            with login(reader) as ro:
                assert ro.execute("SELECT id FROM public.shared").fetchone()[0] == 1
                assert ro.execute("SELECT id FROM another.future").fetchone()[0] == 2
                for query in ("INSERT INTO public.shared(id) VALUES(3)", "CREATE TABLE public.denied(id int)",
                              "ALTER TABLE public.shared ADD COLUMN denied int"):
                    try:
                        ro.execute(query)
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError("Read-only identity gained write/schema access")
            try:
                with login(a, beta):
                    raise AssertionError("Writer connected to a foreign resource")
            except psycopg.OperationalError:
                pass
            with login(a) as writer:
                writer.execute("RESET ROLE")
                for query in ("CREATE EXTENSION IF NOT EXISTS plpgsql",
                              sql.SQL("ALTER ROLE {} SUPERUSER").format(sql.Identifier(catalog.login(a["credential_id"]))),
                              sql.SQL("ALTER ROLE {} VALID UNTIL 'infinity'").format(sql.Identifier(catalog.login(a["credential_id"]))),
                              sql.SQL("DROP DATABASE {}").format(sql.Identifier(catalog.identifier(beta["resource_id"])))):
                    try:
                        writer.execute(query)
                    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectInUse):
                        pass
                    else:
                        raise AssertionError("Resource writer gained administrator/expiry authority")
            held = login(a)
            held.execute("SELECT 1")
            provider.revoke(alpha, a)
            try:
                held.execute("SELECT 1")
            except psycopg.OperationalError:
                pass
            else:
                raise AssertionError("Revoked session remained usable")
            held.close()
            try:
                with login(a):
                    raise AssertionError("Revoked credential authenticated")
            except psycopg.OperationalError:
                pass
            expired = {**b, "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
            provider.issue(alpha, expired)
            try:
                with login(b):
                    raise AssertionError("Expired credential authenticated")
            except psycopg.OperationalError:
                pass
            with login(reader) as ro:
                assert ro.execute("SELECT count(*) FROM public.shared").fetchone()[0] == 1
            # Worker restart and bounded automatic application rotation.
            with conn.transaction():
                binding = catalog.request_binding(conn, "alpha", BindingRequest(resource_id=alpha["resource_id"],
                    component="web", mode="read-write"), "fixture-admin")
            with patch("app.stores.providers.get", return_value=provider):
                for _ in range(2):
                    with conn.transaction():
                        catalog.lock(conn); worker.reconcile(conn)
                previous = conn.execute("SELECT credential_id FROM store_credentials WHERE grant_id=%s AND state='active'",
                    (binding["grant_id"],)).fetchone()[0]
                conn.execute("UPDATE store_credentials SET issued_at=now()-interval '31 days' WHERE credential_id=%s", (previous,))
                with conn.transaction():
                    catalog.lock(conn); worker.reconcile(conn)
                deadline = conn.execute("SELECT handover_deadline FROM store_credentials WHERE credential_id=%s", (previous,)).fetchone()[0]
                with patch.object(provider, "issue", side_effect=RuntimeError("synthetic outage")):
                    with conn.transaction():
                        catalog.lock(conn); worker.reconcile(conn)
                assert conn.execute("SELECT handover_deadline FROM store_credentials WHERE credential_id=%s", (previous,)).fetchone()[0] == deadline
                assert conn.execute("SELECT count(*) FROM store_credentials WHERE grant_id=%s AND state='issuing'", (binding["grant_id"],)).fetchone()[0] == 1
                with conn.transaction():
                    catalog.lock(conn); worker.reconcile(conn)
                assert conn.execute("SELECT state FROM store_credentials WHERE credential_id=%s", (previous,)).fetchone()[0] == "revoked"
                active = conn.execute("SELECT row_to_json(c) FROM store_credentials c WHERE grant_id=%s AND state='active'", (binding["grant_id"],)).fetchone()[0]
            # Real PG authentication and a real query through the identity-bound
            # relay; closure at expiry does not depend on the cleanup worker.
            async def relay_check():
                lease = {"credential_id": active["credential_id"], "resource_id": alpha["resource_id"],
                    "provider": "postgresql", "expires_at": datetime.now(timezone.utc) + timedelta(seconds=1)}
                relay = Relay(backend=lambda value: ("127.0.0.1", port))
                relay.leases = {20000: lease}; relay.last_success = time.monotonic()
                server = await asyncio.start_server(lambda r,w: relay.handle(20000,r,w), "127.0.0.1", 0)
                def query():
                    client = psycopg.connect(host="127.0.0.1", port=server.sockets[0].getsockname()[1],
                        dbname=catalog.identifier(alpha["resource_id"]), user=catalog.login(active["credential_id"]),
                        password=catalog.secret_for(active["credential_id"]), sslmode="prefer", autocommit=True)
                    assert client.execute("SELECT id FROM public.shared").fetchone()[0] == 1
                    time.sleep(1.2)
                    try:
                        client.execute("SELECT 1")
                    except psycopg.OperationalError:
                        pass
                    else:
                        raise AssertionError("Expired relay session remained usable")
                    client.close()
                try:
                    await asyncio.wait_for(asyncio.to_thread(query), 5)
                finally:
                    server.close(); await server.wait_closed()
            asyncio.run(relay_check())
            # Retiring/purging one resource must not touch the other database.
            all_credentials = conn.execute("SELECT row_to_json(c) FROM store_credentials c JOIN store_grants g USING(grant_id) WHERE g.resource_id=%s", (alpha["resource_id"],)).fetchall()
            for (cred,) in all_credentials:
                provider.revoke(alpha, cred)
            provider.purge(alpha)
            assert conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (catalog.identifier(beta["resource_id"]),)).fetchone()
        print("PASS named PostgreSQL: separate databases; cross-writer DDL; future-schema reads; read-only write/DDL denial; foreign-resource denial; no admin/expiry escalation; revoked session closure; expired login denial; 30-day worker rotation/retry/one-hour deadline; real relay authentication/session expiry; isolated purge")
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, timeout=30)


if __name__ == "__main__":
    main()
