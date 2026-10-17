"""Restore an encrypted fixture backup into an empty, temporary PostgreSQL server.

This never points at the platform installation or an off-host repository. The
caller supplies its disposable restic environment and fixture resource records.
"""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql

from app.stores import catalog, recovery
from app.stores.contract import HumanGrant
from app.stores.postgres import Postgres


def command(arguments, **kwargs):
    result = subprocess.run(arguments, capture_output=True, timeout=60, **kwargs)
    if result.returncode:
        raise RuntimeError('Disposable encrypted restore command failed')
    return result.stdout


def verify(binary, snapshot, source_image, alpha, beta, purging, old_credential):
    """Exercise actual pg_dumpall restoration, not a catalog-state simulation."""
    name = 'named-store-restore-' + uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    started = time.monotonic()
    image = os.environ.get('NAMED_POSTGRES_RECOVERY_IMAGE', source_image)
    with tempfile.TemporaryDirectory(prefix='named-store-restored-') as directory:
        command([binary, 'restore', snapshot, '--target', directory])
        manifests = list(Path(directory).rglob('manifest.json'))
        if len(manifests) != 1:
            raise AssertionError('Restored fixture manifest is ambiguous')
        bundle = manifests[0].parent
        manifest = json.loads(manifests[0].read_bytes())
        for filename in ('postgres.sql.gz', 'store-recovery.json'):
            if hashlib.sha256((bundle / filename).read_bytes()).hexdigest() != manifest['sha256'][filename]:
                raise AssertionError('Restored fixture checksum mismatch')
        intents = json.loads((bundle / 'store-recovery.json').read_bytes())
        try:
            command(['docker', 'run', '-d', '--name', name, '--memory', '512m', '--cpus', '1',
                '-e', 'POSTGRES_PASSWORD', '-p', '127.0.0.1::5432',
                '--tmpfs', '/var/lib/postgresql:rw,size=256m', image],
                env={**os.environ, 'POSTGRES_PASSWORD': password})
            port = int(command(['docker', 'port', name, '5432/tcp']).decode().strip().rsplit(':', 1)[1])

            def connect(database):
                # Local Docker exec uses the image's peer/trust socket, independent
                # of the restored postgres password, which pg_dumpall replaces.
                return psycopg.connect(host='127.0.0.1', port=port, dbname=database,
                    user='postgres', password=password, autocommit=True, connect_timeout=2)

            for _ in range(80):
                try:
                    with connect('postgres'):
                        break
                except psycopg.OperationalError:
                    time.sleep(.25)
            else:
                raise AssertionError('Empty restore server did not become ready')
            with gzip.open(bundle / 'postgres.sql.gz', 'rb') as stream:
                loaded = subprocess.run(['docker', 'exec', '-i', name, 'psql', '-X',
                    '-U', 'postgres', '-d', 'postgres'], input=stream.read(), capture_output=True, timeout=60)
            if loaded.returncode:
                raise AssertionError('Encrypted fixture SQL import failed')
            location = Path(__file__).resolve().parents[1] / 'operations/backup/scripts/restore-recovery.py'
            spec = importlib.util.spec_from_file_location('store_fixture_restore', location)
            restore = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(restore)
            restore.check_import_errors(loaded.stderr.decode())
            # Rotate only this disposable root identity after import. This keeps
            # the fixture connection separate from the source server's root key.
            statement = sql.SQL('ALTER ROLE postgres PASSWORD {}').format(sql.Literal(password)).as_string()
            command(['docker', 'exec', '-i', name, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                '-U', 'postgres', '-d', 'postgres'], input=statement.encode())
            provider = Postgres(connect)
            provider.endpoint = lambda: ('127.0.0.1', port)
            with connect('postgres') as conn:
                with conn.transaction():
                    recovery.quarantine(conn)
                assert recovery.required(conn)
                from app.stores.relay import snapshot as relay_snapshot
                from contextlib import nullcontext
                with patch('app.stores.relay.connect', return_value=nullcontext(conn)):
                    assert relay_snapshot() == {}
                # A restored schema alone must not be mistaken for AGE recovery.
                if 'age' in alpha['extensions']:
                    try:
                        provider.validate_recovery(alpha)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('Expected raw logical AGE restore failure')
                with patch('app.stores.providers.get', return_value=provider):
                    with conn.transaction():
                        catalog.lock(conn)
                        plan = recovery.reconcile(conn, intents)
                        assert not plan['applied'] and recovery.required(conn)
                        assert recovery.reconcile(conn, intents, apply=True)['applied']
                assert not recovery.required(conn)
                assert conn.execute("SELECT count(*) FROM store_grants WHERE state<>'revoked'").fetchone()[0] == 0
                assert conn.execute("SELECT count(*) FROM store_credentials WHERE state<>'revoked'").fetchone()[0] == 0
                assert not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',
                    (catalog.identifier(purging['resource_id']),)).fetchone()
                assert catalog.resource(conn, purging['resource_id'])['state'] == 'purged'
                assert conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',
                    (catalog.identifier(beta['resource_id']),)).fetchone()
                with conn.transaction():
                    grant = catalog.create_human_grant(conn, catalog.resource(conn, alpha['resource_id']),
                        HumanGrant(issuer='https://fixture.invalid', subject='fresh-recovery-reader', mode='read-only'),
                        'fresh-fixture-approval')
                    credential = catalog.issue(conn, grant)
                provider.issue(alpha, credential)

            def data_connection(credential):
                return psycopg.connect(host='127.0.0.1', port=port, dbname=catalog.identifier(alpha['resource_id']),
                    user=catalog.login(credential['credential_id']), password=catalog.secret_for(credential['credential_id']),
                    connect_timeout=2, autocommit=True)

            try:
                with data_connection(old_credential):
                    raise AssertionError('Recovered credential was reactivated')
            except psycopg.OperationalError:
                pass
            with data_connection(credential) as reader:
                assert reader.execute('SELECT count(*) FROM public.shared').fetchone()[0] == 1
                assert reader.execute('SELECT count(*) FROM reference.datasets').fetchone()[0] == 1
                assert reader.execute('SELECT count(*) FROM reference.outbox').fetchone()[0] == 1
                if 'vector' in alpha['extensions']:
                    assert reader.execute("SELECT id FROM public.embeddings ORDER BY embedding <-> '[1,2,3]'::vector LIMIT 1").fetchone()[0] == 1
                if 'age' in alpha['extensions']:
                    assert reader.execute("SELECT * FROM cypher('fixture_graph', $$ MATCH (n:Node) RETURN count(n) $$) AS (v agtype)").fetchone()[0] == '2'
                    assert reader.execute("SELECT * FROM cypher('dependency_cycle', $$ MATCH (a)-[:DEPENDS]->(b) RETURN count(b) $$) AS (v agtype)").fetchone()[0] == '3'
                try:
                    reader.execute('INSERT INTO public.shared(id) VALUES(97)')
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError('Fresh recovered reader could write')
            print(f'PASS encrypted restic restore into empty server: real SQL/catalog/data, quarantine, purge replay, graph/vector recovery, old-key denial and fresh read-only approval ({time.monotonic() - started:.1f}s; disposable fixture only)')
        finally:
            command(['docker', 'rm', '-f', name])
