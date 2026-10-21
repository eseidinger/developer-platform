#!/usr/bin/env python3
"""Disposable real PostgreSQL tests for named resources and cross-writer ownership."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import json
import asyncio
from unittest.mock import patch
import os
import secrets
import subprocess
import time
from contextlib import contextmanager, nullcontext
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
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise RuntimeError("Disposable PostgreSQL fixture operation failed") from None


def main():
    name = "named-postgres-" + uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    os.environ["DATABASE_KEY"] = secrets.token_hex(32)
    try:
        run("docker", "run", "-d", "--name", name, "--memory", "512m", "--cpus", "1",
            "-e", "POSTGRES_PASSWORD=" + password, "-p", "127.0.0.1::5432",
            "--tmpfs", "/var/lib/postgresql:rw,size=256m", os.environ.get("NAMED_POSTGRES_IMAGE", "postgres:18.6-trixie"))
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
                alpha = catalog.create_resource(conn, "alpha", ResourceCreate(name="primary", provider="postgresql", extensions=["vector", "age"] if os.environ.get("NAMED_POSTGRES_EXTENSIONS") == "1" else []))
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
                    assert (datetime.fromisoformat(cred["expires_at"]) - datetime.fromisoformat(cred["issued_at"])).total_seconds() == 86400
                    credentials.append(cred)
                provider.issue(alpha, cred)
            def login(credential, resource=alpha):
                return psycopg.connect(host="127.0.0.1", port=port,
                    dbname=catalog.identifier(resource["resource_id"]), user=catalog.login(credential["credential_id"]),
                    password=catalog.secret_for(credential["credential_id"]), autocommit=True, connect_timeout=2)
            a, b, reader = credentials
            with login(a) as writer:
                if os.environ.get('STORE_ANALYTICS_FIXTURE') == '1':
                    from scripts.tests.support.store_analytics_fixture import postgres as analytics_comparison
                    analytics_comparison(writer)
                reference = Path(__file__).resolve().parents[4] / "examples/postgresql-reference/baseline.sql"
                writer.execute(reference.read_text())
                try:
                    with writer.transaction():
                        writer.execute("INSERT INTO reference.datasets(id,title,metadata) VALUES(2,'rolled back','{}')")
                        writer.execute("INSERT INTO reference.outbox(payload) VALUES('{}')")
                        raise RuntimeError("synthetic transaction failure")
                except RuntimeError:
                    pass
                assert writer.execute("SELECT count(*) FROM reference.datasets").fetchone()[0] == 1
                assert writer.execute("SELECT count(*) FROM reference.outbox").fetchone()[0] == 1
                writer.execute("CREATE TABLE public.shared(id INTEGER)")
                writer.execute("INSERT INTO public.shared VALUES(1)")
                writer.execute("CREATE SCHEMA another")
                writer.execute("CREATE TABLE another.future(id INTEGER)")
                writer.execute("INSERT INTO another.future VALUES(2)")
                try:
                    writer.execute("CREATE FUNCTION public.privilege_bypass() RETURNS void LANGUAGE sql SECURITY DEFINER AS $$ INSERT INTO public.shared(id) VALUES(44) $$")
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Writer created a security-definer privilege bypass")
                writer.execute("CREATE FUNCTION public.write_via_function() RETURNS void LANGUAGE sql AS $$ INSERT INTO public.shared(id) VALUES(44) $$")
                for statement in ("GRANT INSERT ON public.shared TO PUBLIC", "ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO PUBLIC"):
                    try:
                        writer.execute(statement)
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError("Writer bypassed managed access permissions")
            with login(b) as writer:
                writer.execute("ALTER TABLE public.shared ADD COLUMN note TEXT")
                writer.execute("UPDATE public.shared SET note='changed by second writer'")
            with login(reader) as ro:
                assert ro.execute("SELECT id FROM public.shared").fetchone()[0] == 1
                assert ro.execute("SELECT id FROM another.future").fetchone()[0] == 2
                assert ro.execute("SELECT id FROM reference.datasets WHERE metadata @> '{\"kind\":\"energy\"}'::jsonb").fetchone()[0] == 1
                assert ro.execute("SELECT id FROM reference.datasets WHERE search @@ websearch_to_tsquery('english','solar')").fetchone()[0] == 1
                assert ro.execute("WITH RECURSIVE reachable(id) AS (VALUES(1) UNION SELECT d.child FROM reference.dependencies d JOIN reachable r ON d.parent=r.id) SELECT count(*) FROM reachable").fetchone()[0] == 3
                assert ro.execute("SELECT total FROM reference.monthly").fetchone()[0] == 6
                assert ro.execute("SELECT count(*) FROM reference.measurements_2026").fetchone()[0] == 2

                for query in ("SELECT public.write_via_function()", "INSERT INTO public.shared(id) VALUES(3)", "CREATE TABLE public.denied(id int)",
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
                try:
                    writer.execute("CREATE EXTENSION hstore")
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Resource writer installed a trusted extension")
                writer.execute("SET ROLE NONE")
                assert writer.execute("SELECT current_user").fetchone()[0] == catalog.login(a["credential_id"])
                for query in ("CREATE TABLE public.wrong_owner(id int)", "CREATE SCHEMA wrong_owner",
                              sql.SQL("ALTER ROLE {} SUPERUSER").format(sql.Identifier(catalog.login(a["credential_id"]))),
                              sql.SQL("ALTER ROLE {} VALID UNTIL 'infinity'").format(sql.Identifier(catalog.login(a["credential_id"]))),
                              sql.SQL("DROP DATABASE {}").format(sql.Identifier(catalog.identifier(beta["resource_id"])))):
                    try:
                        writer.execute(query)
                    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectInUse):
                        pass
                    else:
                        raise AssertionError("Resource writer gained administrator/expiry authority")
            if alpha["extensions"]:
                with login(a) as writer:
                    writer.execute("CREATE TABLE public.embeddings(id int, embedding vector(3))")
                    writer.execute("INSERT INTO public.embeddings VALUES(1,'[1,2,3]'),(2,'[4,5,6]')")
                    writer.execute("CREATE INDEX ON public.embeddings USING hnsw(embedding vector_l2_ops)")
                    from app.stores import projections
                    graph_source = {"format": 1, "graph": "fixture_graph", "indexes": [
                        {"name": "node_properties", "label": "Node", "kind": "properties-gin"},
                        {"name": "node_keys", "label": "Node", "kind": "source-key-unique"}], "vertices": [
                        {"key": "first", "label": "Node", "properties": {"id": 1, "name": "quoted ' \" $$ marker", "zero": -0.0}},
                        {"key": "second", "label": "Node", "properties": {"id": 2}}],
                        "edges": [{"source": "first", "target": "second", "label": "LINK"}]}
                    projections.append(writer, graph_source)
                    for query in ("DELETE FROM platform_control.graph_sources", "DROP TABLE platform_control.graph_sources"):
                        try:
                            writer.execute(query)
                        except psycopg.errors.InsufficientPrivilege:
                            pass
                        else:
                            raise AssertionError("Writer altered protected source history")
                with login(reader) as ro:
                    assert ro.execute("SELECT id FROM public.embeddings ORDER BY embedding <-> '[1,2,3]'::vector LIMIT 1").fetchone()[0] == 1
                    assert ro.execute("SELECT * FROM cypher('fixture_graph', $$ MATCH (n:Node) RETURN count(n) $$) AS (v agtype)").fetchone()[0] == '2'
                    try:
                        ro.execute("SELECT * FROM cypher('fixture_graph', $$ CREATE (:Node {id: 3}) $$) AS (v agtype)")
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError("AGE reader gained graph write rights")
                with login(b) as writer:
                    writer.execute("SELECT * FROM cypher('fixture_graph', $$ MATCH (n:Node) SET n.changed = true RETURN n $$) AS (v agtype)")
                    for vertex in graph_source["vertices"]:
                        vertex["properties"]["changed"] = True
                    projections.append(writer, graph_source)
                    before = writer.execute("SELECT count(*) FROM platform_control.graph_sources").fetchone()[0]
                    writer.execute('CREATE VIEW public.graph_dependent AS SELECT id FROM fixture_graph."Node"')
                    try:
                        projections.append(writer, graph_source)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Projection replacement cascaded into an application view")
                    assert writer.execute("SELECT count(*) FROM platform_control.graph_sources").fetchone()[0] == before
                    assert writer.execute("SELECT count(*) FROM public.graph_dependent").fetchone()[0] == 2
                    writer.execute("DROP VIEW public.graph_dependent")
                    for query in ("DROP EXTENSION vector CASCADE", "DROP EXTENSION age CASCADE"):
                        try:
                            writer.execute(query)
                        except psycopg.errors.InsufficientPrivilege:
                            pass
                        else:
                            raise AssertionError("Writer removed a managed extension")
                # A second graph covers different labels, directed cycles and
                # independent protected snapshots in the same resource.
                with login(b) as writer:
                    cycle_source = {"graph": "dependency_cycle", "vertices": [
                        {"key": "api", "label": "Component"}, {"key": "db", "label": "Store"},
                        {"key": "worker", "label": "Component"}], "edges": [
                        {"source": "api", "target": "db", "label": "DEPENDS"},
                        {"source": "db", "target": "worker", "label": "DEPENDS"},
                        {"source": "worker", "target": "api", "label": "DEPENDS"}]}
                    projections.append(writer, cycle_source)
                restored_name = "projection_restore_" + uuid4().hex[:12]
                database = catalog.identifier(alpha["resource_id"])
                data = subprocess.check_output(["docker","exec",name,"pg_dump","-U","postgres","-Fc",database], timeout=30)
                conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(restored_name)))
                loaded = subprocess.run(["docker","exec","-i",name,"pg_restore","-U","postgres","--exit-on-error","-d",restored_name],
                    input=data, capture_output=True, timeout=30)
                assert loaded.returncode == 0, "Disposable projection pg_restore failed: " + loaded.stderr.decode()[-1800:]
                # Single-database pg_dump excludes database ACLs. Reapply them
                # for this renamed clone; pg_dumpall preserves original DB ACLs.
                conn.execute(sql.SQL("GRANT CONNECT,CREATE,TEMPORARY ON DATABASE {} TO {}")
                    .format(sql.Identifier(restored_name), sql.Identifier(database + "_owner")))
                conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
                    .format(sql.Identifier(restored_name), sql.Identifier(database + "_reader")))
                restored_provider = Postgres(lambda target: connect(restored_name if target == database else target))
                try:
                    restored_provider.validate_recovery(alpha)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Expected the recorded AGE logical-restore OID limitation")
                result = restored_provider.rebuild_projections(alpha)
                assert result == {"graphs": 2, "vertices": 5, "edges": 4}
                restored_provider.validate_recovery(alpha)
                with connect(restored_name) as restored:
                    restored.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(database + "_reader")))
                    restored.execute("SET search_path=ag_catalog,public,platform_extensions")
                    assert restored.execute("SELECT * FROM cypher('fixture_graph', $$ MATCH (n:Node) RETURN count(n) $$) AS (v agtype)").fetchone()[0] == '2'
                    assert restored.execute("SELECT * FROM cypher('dependency_cycle', $$ MATCH (a)-[:DEPENDS]->(b) RETURN count(b) $$) AS (v agtype)").fetchone()[0] == '3'
                    assert restored.execute("SELECT id FROM public.embeddings ORDER BY embedding <-> '[1,2,3]'::vector LIMIT 1").fetchone()[0] == 1
                    assert restored.execute("SELECT id FROM public.shared").fetchone()[0] == 1
                    assert restored.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='fixture_graph' AND indexname IN ('projection_node_properties','projection_node_keys')").fetchone()[0] == 2
                    text_value = restored.execute("SELECT * FROM cypher('fixture_graph', $$ MATCH (n:Node {id: 1}) RETURN n.name $$) AS (v agtype)").fetchone()[0]
                    assert json.loads(text_value) == graph_source["vertices"][0]["properties"]["name"]
                    assert restored.execute("SELECT * FROM cypher('fixture_graph', $$ MATCH (n:Node) WHERE n.changed=true RETURN count(n) $$) AS (v agtype)").fetchone()[0] == '2'
                conn.execute(sql.SQL("DROP DATABASE {} WITH(FORCE)").format(sql.Identifier(restored_name)))
                print("PASS real AGE logical restore reproduces stale OIDs; native graph rebuild from protected snapshots restores two graphs/five labels/cycle; SQL and pgvector retained")
                print("PASS selected pgvector HNSW and AGE: both writers; reader queries; denied graph writes and extension removal")
            old_reader_deadline = conn.execute("SELECT expires_at FROM store_credentials WHERE credential_id=%s",
                (reader["credential_id"],)).fetchone()[0]
            with login(reader) as existing_reader:
                with conn.transaction():
                    renewed_reader = catalog.issue(conn, catalog.grant(conn, reader["grant_id"]))
                provider.issue(alpha, renewed_reader)
                assert conn.execute("SELECT expires_at FROM store_credentials WHERE credential_id=%s",
                    (reader["credential_id"],)).fetchone()[0] == old_reader_deadline
                assert renewed_reader["credential_id"] != reader["credential_id"]
                assert (datetime.fromisoformat(renewed_reader["expires_at"]) - datetime.fromisoformat(renewed_reader["issued_at"])).total_seconds() == 86400
                assert existing_reader.execute("SELECT id FROM public.shared").fetchone()[0] == 1
                with login(renewed_reader) as renewed:
                    assert renewed.execute("SELECT id FROM public.shared").fetchone()[0] == 1
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
            # Real catalog constraints for native console child sessions. Relabel
            # only inside a rolled-back metadata transaction; no S3 service or
            # live resource is touched by this database fixture.
            from app.stores import console as store_console
            with conn.transaction(force_rollback=True), patch.dict(os.environ, {
                    'STORE_CONSOLE_HTTP_ENABLED': 'true', 'STORE_ENABLED_PROVIDERS': 'postgresql,s3'}), \
                    patch.object(store_console, 'PROVIDERS', {'s3', 'qdrant'}):
                conn.execute("UPDATE store_resources SET provider='s3' WHERE resource_id=%s", (alpha['resource_id'],))
                personal = store_console.lease(conn, reader['credential_id'])
                assert personal is not None and personal['kind'] == 'human'
                for index in range(16):
                    store_console.record_session(conn, personal, f'C{index:019d}', f'{index:064x}',
                        datetime.now(timezone.utc) + timedelta(hours=48))
                assert conn.execute('SELECT max(expires_at) FROM store_console_sessions').fetchone()[0] == personal['expires_at']
                store_console.record_session(conn, personal, 'C' + '0' * 19, '0' * 64, personal['expires_at'])
                try:
                    store_console.record_session(conn, personal, 'X' * 20, 'a' * 64, personal['expires_at'])
                except ValueError:
                    pass
                else:
                    raise AssertionError('Console child-session capacity was not enforced')
                other_human = store_console.lease(conn, b['credential_id'])
                assert other_human is not None
                try:
                    store_console.record_session(conn, other_human, 'C' + '0' * 19, '0' * 64, other_human['expires_at'])
                except ValueError:
                    pass
                else:
                    raise AssertionError('A native session was retargeted to another human lease')
                conn.execute('UPDATE store_grants SET version=version+1 WHERE grant_id=%s', (reader['grant_id'],))
                assert store_console.lease(conn, reader['credential_id']) is None
                try:
                    store_console.record_session(conn, personal, 'Y' * 20, 'b' * 64, personal['expires_at'])
                except ValueError:
                    pass
                else:
                    raise AssertionError('A changed grant registered a stale console session')
            assert conn.execute('SELECT count(*) FROM store_console_sessions').fetchone()[0] == 0
            assert conn.execute('SELECT provider FROM store_resources WHERE resource_id=%s', (alpha['resource_id'],)).fetchone()[0] == 'postgresql'
            print('PASS real console-session catalog: exact ownership, idempotent registration, 16-session cap, original deadline clamp and stale-grant denial')
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
            if os.environ.get("NAMED_POSTGRES_CONSOLE") == "1":
                async def console_check():
                    from scripts.tests.support.store_console_fixture import run as console_run
                    lease = {"credential_id": reader["credential_id"], "resource_id": alpha["resource_id"],
                        # Keep the lease valid through both bounded console startup
                        # waits. The browser check expires it explicitly via control.
                        "provider": "postgresql", "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}
                    relay = Relay(backend=lambda value: ("127.0.0.1", port))
                    relay.leases = {20000: lease}; relay.last_success = time.monotonic()
                    server = await asyncio.start_server(lambda r,w: relay.handle(20000,r,w), "127.0.0.1", 0)
                    async def expire(reader, writer):
                        await reader.readuntil(b"\r\n\r\n")
                        lease["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                        await writer.drain(); writer.close()
                    control = await asyncio.start_server(expire, "127.0.0.1", 0)
                    async def heartbeat():
                        while True:
                            relay.last_success = time.monotonic()
                            await asyncio.sleep(.5)
                    beat = asyncio.create_task(heartbeat())
                    connection = {"PGHOST": "127.0.0.1", "PGPORT": str(server.sockets[0].getsockname()[1]),
                        "PGDATABASE": catalog.identifier(alpha["resource_id"]), "PGUSER": catalog.login(reader["credential_id"]),
                        "PGPASSWORD": catalog.secret_for(reader["credential_id"])}
                    try:
                        await asyncio.to_thread(console_run, connection, f"http://127.0.0.1:{control.sockets[0].getsockname()[1]}/expire")
                    finally:
                        beat.cancel()
                        await asyncio.gather(beat, return_exceptions=True)
                        server.close(); control.close()
                        await server.wait_closed(); await control.wait_closed()
                asyncio.run(console_check())
            if os.environ.get("RESTIC_TEST_BINARY"):
                import importlib.util
                import tempfile
                from app.stores.contract import Purge
                location = Path(__file__).resolve().parents[4] / "operations/backup/scripts/backup-platform.py"
                spec = importlib.util.spec_from_file_location("store_fixture_backup", location)
                backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)
                with conn.transaction():
                    doomed = catalog.create_resource(conn, "alpha", ResourceCreate(name="purge-intent", provider="postgresql"))
                provider.provision(doomed)
                conn.execute("UPDATE store_resources SET observed_state='active' WHERE resource_id=%s", (doomed["resource_id"],))
                with conn.transaction():
                    doomed = catalog.retire(conn, catalog.resource(conn, doomed["resource_id"]), 1)
                    with patch("app.stores.providers.get", return_value=provider):
                        worker.reconcile(conn)
                    doomed = catalog.resource(conn, doomed["resource_id"])
                    doomed = catalog.request_purge(conn, doomed, Purge(version=doomed["version"],
                        confirm_resource_id=doomed["resource_id"], confirm_owner_project="alpha"))
                with patch("app.stores.providers.get", return_value=provider):
                    with conn.transaction():
                        worker.reconcile(conn)
                assert catalog.resource(conn, doomed["resource_id"])["error_code"] == "PurgeAwaitingVerifiedBackup"
                assert conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (catalog.identifier(doomed["resource_id"]),)).fetchone()
                with tempfile.TemporaryDirectory(prefix="store-intent-backup-") as directory:
                    binary = os.environ["RESTIC_TEST_BINARY"]
                    job = backup.Job({"platform_dir": directory, "state_dir": directory + "/state", "restic": binary,
                        "instance": "store-fixture", "watchdog_url": "https://fixture.invalid/unused", "watchdog_token": "unused"})
                    def psql(*arguments):
                        target = arguments[arguments.index("-d") + 1]
                        def execute(connection):
                            cursor = connection.execute(arguments[-1])
                            if cursor.description:
                                value = cursor.fetchone()[0]
                                return ("t" if value is True else "f" if value is False else json.dumps(value)).encode()
                            return b""
                        if target == "platform":
                            return execute(conn)
                        with connect(target) as connection:
                            return execute(connection)
                    def postgres_argv(*arguments):
                        return ["docker", "exec", "-i", name,
                            *("postgres" if value == "platform" else value for value in arguments)]
                    def capture_database_intent(bundle):
                        with job.catalog_snapshot():
                            with connect("postgres") as competitor:
                                assert not competitor.execute("SELECT pg_try_advisory_lock(731904)").fetchone()[0]
                            job.check_graph_sources()
                            job.dump(bundle)
                            job.store_recovery_manifest(bundle)
                        assert conn.execute("SELECT pg_try_advisory_lock(731904)").fetchone()[0]
                        conn.execute("SELECT pg_advisory_unlock(731904)")
                    with patch.dict(os.environ, {"RESTIC_REPOSITORY": directory + "/repo", "RESTIC_PASSWORD": secrets.token_urlsafe(32), "RESTIC_CACHE_DIR": directory + "/cache"}):
                        subprocess.run([binary, "init"], check=True, capture_output=True, timeout=30)
                        with patch.object(job, "compose", side_effect=psql), patch.object(job, "notify"), \
                                patch.object(job, "postgres_argv", side_effect=postgres_argv), \
                                patch.object(job, "capture", side_effect=capture_database_intent):
                            # A temporary metadata-only S3 placeholder exercises
                            # the actual cross-store pause without a live service.
                            conn.execute("UPDATE store_resources SET provider='s3' WHERE resource_id=%s", (beta['resource_id'],))
                            with conn.transaction():
                                pause_grant = catalog.create_human_grant(conn, alpha,
                                    HumanGrant(issuer='https://fixture.invalid', subject='backup-quiescence', mode='read-only'), 'fixture-admin')
                                pause_credential = catalog.issue(conn, pause_grant)
                            provider.issue(alpha, pause_credential)
                            held_pause = login(pause_credential)
                            try:
                                try:
                                    with job.catalog_snapshot():
                                        assert conn.execute('SELECT backup_until>now() FROM store_control WHERE singleton').fetchone()[0]
                                        from app.stores.relay import snapshot as paused_snapshot
                                        with patch('app.stores.relay.connect', return_value=nullcontext(conn)):
                                            assert paused_snapshot() == {}
                                        try:
                                            held_pause.execute('SELECT 1')
                                        except psycopg.OperationalError:
                                            pass
                                        else:
                                            raise AssertionError('A managed SQL session survived coordinated quiescence')
                                        raise RuntimeError("synthetic interrupted capture")
                                except RuntimeError:
                                    pass
                                assert conn.execute('SELECT backup_until IS NULL FROM store_control WHERE singleton').fetchone()[0]
                            finally:
                                held_pause.close()
                                conn.execute("UPDATE store_resources SET provider='postgresql' WHERE resource_id=%s", (beta['resource_id'],))
                            assert conn.execute("SELECT pg_try_advisory_lock(731904)").fetchone()[0]
                            conn.execute("SELECT pg_advisory_unlock(731904)")
                            if alpha["extensions"]:
                                with connect(catalog.identifier(alpha["resource_id"])) as resource_conn:
                                    resource_conn.execute("SET search_path=ag_catalog,public,platform_extensions")
                                    resource_conn.execute("SELECT ag_catalog.create_graph('unprotected_fixture')")
                                try:
                                    job.check_graph_sources()
                                except backup.BackupError:
                                    pass
                                else:
                                    raise AssertionError("Backup accepted a retained AGE graph without protected sources")
                                with connect(catalog.identifier(alpha["resource_id"])) as resource_conn:
                                    resource_conn.execute("SELECT ag_catalog.drop_graph('unprotected_fixture',true)")
                            assert job.run() == 0
                        from scripts.tests.support.store_recovery_fixture import verify as verify_encrypted_restore
                        verify_encrypted_restore(binary, job.read('status.json', {})['last_verified_snapshot'],
                            os.environ.get('NAMED_POSTGRES_IMAGE', 'postgres:18.6-trixie'),
                            alpha, beta, doomed, renewed_reader)
                    backed = catalog.resource(conn, doomed["resource_id"])
                    assert backed["purge_backup_version"] == backed["version"] and backed["purge_backup_snapshot"]
                with patch("app.stores.providers.get", return_value=provider):
                    with conn.transaction():
                        worker.reconcile(conn)
                assert catalog.resource(conn, doomed["resource_id"])["state"] == "purged"
                assert not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (catalog.identifier(doomed["resource_id"]),)).fetchone()
                verified_purge_intent = catalog.resource(conn, doomed["resource_id"])
                # Model an older data/catalog snapshot reintroducing an already
                # purged resource. Latest verified intent must delete it again.
                provider.provision(doomed)
                conn.execute("UPDATE store_resources SET state='active',observed_state='active',version=1 WHERE resource_id=%s",
                    (doomed["resource_id"],))
                print("PASS purge waits for encrypted restic upload/readback/verification before worker deletion; catalog snapshot lock covers real SQL dump and intent capture (local repository)")
            from app.stores import monitoring as store_monitoring, recovery
            from app.stores.relay import snapshot
            with patch("app.stores.providers.get", return_value=provider):
                with conn.transaction():
                    store_monitoring.sample(conn)
                measured = catalog.resource(conn, alpha["resource_id"])
                assert measured["used_bytes"] > 0 and measured["usage_measured_at"] and not measured["usage_error"]
                with patch.object(provider, "usage", side_effect=RuntimeError("synthetic measurement outage")):
                    conn.execute("UPDATE store_resources SET usage_attempt_at=now()-interval '2 minutes'")
                    with conn.transaction():
                        store_monitoring.sample(conn)
                failed = catalog.resource(conn, alpha["resource_id"])
                assert failed["used_bytes"] == measured["used_bytes"] and failed["usage_error"]
                with conn.transaction():
                    recovery.quarantine(conn)
                    assert recovery.required(conn)
                    try:
                        catalog.issue(conn, catalog.grant(conn, binding["grant_id"]))
                    except catalog.Conflict:
                        pass
                    else:
                        raise AssertionError("Recovered catalog issued credentials before reconciliation")
                with patch("app.stores.relay.connect", return_value=nullcontext(conn)):
                    assert snapshot() == {}
                with conn.transaction():
                    worker.reconcile(conn)
                assert conn.execute("SELECT count(*) FROM store_credentials WHERE state<>'revoked'").fetchone()[0] == 0
            manifest = {"format": 1, "captured_at": datetime.now(timezone.utc).isoformat(), "resources": []}
            for (record,) in conn.execute("SELECT row_to_json(r) FROM store_resources r").fetchall():
                if os.environ.get("RESTIC_TEST_BINARY") and record["resource_id"] == doomed["resource_id"]:
                    record = verified_purge_intent
                manifest["resources"].append({key: record[key] for key in (
                    "resource_id", "owner_project", "name", "provider", "state", "version", "quota_bytes", "extensions")})
            with patch("app.stores.providers.get", return_value=provider):
                with conn.transaction():
                    plan = recovery.reconcile(conn, manifest)
                    assert not plan["applied"] and recovery.required(conn)
                    assert recovery.reconcile(conn, manifest, apply=True)["applied"]
            assert not recovery.required(conn)
            if os.environ.get("RESTIC_TEST_BINARY"):
                assert not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (catalog.identifier(doomed["resource_id"]),)).fetchone()
                assert catalog.resource(conn, doomed["resource_id"])["state"] == "purged"
            assert not conn.execute("SELECT 1 FROM store_grants WHERE state='active' LIMIT 1").fetchone()
            with conn.transaction():
                renewed = catalog.create_human_grant(conn, catalog.resource(conn, alpha["resource_id"]),
                    HumanGrant(issuer="https://fixture.invalid", subject="fresh-approval", mode="read-only"), "fixture-admin")
                fresh = catalog.issue(conn, renewed)
            provider.issue(alpha, fresh)
            with login(fresh) as client:
                assert client.execute("SELECT id FROM public.shared").fetchone()[0] == 1
            try:
                with login(active):
                    raise AssertionError("A recovered old credential was resurrected")
            except psycopg.OperationalError:
                pass
            print("PASS measured nonzero usage; retained stale reading on failure; recovered issuance/relay denial; latest intents replayed; only fresh approval restores access")
            # Retiring/purging one resource must not touch the other database.
            all_credentials = conn.execute("SELECT row_to_json(c) FROM store_credentials c JOIN store_grants g USING(grant_id) WHERE g.resource_id=%s", (alpha["resource_id"],)).fetchall()
            for (cred,) in all_credentials:
                provider.revoke(alpha, cred)
            provider.purge(alpha)
            assert conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (catalog.identifier(beta["resource_id"]),)).fetchone()
            with conn.transaction():
                catalog.retire_project(conn, "beta")
            assert conn.execute("SELECT status FROM projects WHERE name='beta'").fetchone()[0] == "applied"
            try:
                catalog.active_project(conn, "beta")
            except catalog.Conflict:
                pass
            else:
                raise AssertionError("Retiring project admitted a new resource while namespace cleanup was pending")
            print("PASS project-retirement fence denies admission before project status changes")
        print("PASS named PostgreSQL: separate databases; cross-writer DDL; future-schema reads; read-only write/DDL denial; foreign-resource denial; no admin/expiry escalation; revoked session closure; expired login denial; 30-day worker rotation/retry/one-hour deadline; real relay authentication/session expiry; isolated purge")
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, timeout=30)


if __name__ == "__main__":
    main()
