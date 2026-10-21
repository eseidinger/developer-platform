#!/usr/bin/env python3
"""Native Qdrant JWT isolation/revocation and real HTTP lease-stream fixture."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
from datetime import datetime, timedelta, timezone
import os
import secrets
import subprocess
import time
from uuid import uuid4

import httpx
from app.stores.qdrant import Qdrant, collection, VALIDATION
from app.stores.http_client import PrivateJSON
from app.stores.relay import Relay
from app.stores.s3 import StoreError
from scripts.fixtures.store_volume_fixture import restored

IMAGE = 'qdrant/qdrant:v1.19.2@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad'


def command(*arguments, env=None):
    result = subprocess.run(arguments, capture_output=True, timeout=60, env=env)
    if result.returncode:
        raise RuntimeError('Disposable Qdrant fixture command failed')
    return result.stdout.decode().strip()


def denied(operation):
    try:
        operation()
    except StoreError as error:
        assert str(error) in {'Provider request failed (401)', 'Provider request failed (403)'}, str(error)
    else:
        raise AssertionError('Scoped Qdrant token exceeded its permissions')


def main():
    name = 'named-qdrant-' + uuid4().hex[:12]
    volume = name + '-data'
    key = secrets.token_hex(32)
    monitor_key = secrets.token_hex(32)
    os.environ['STORE_MONITOR_PASSWORD'] = monitor_key
    env = {**os.environ, 'QDRANT__SERVICE__API_KEY': key, 'QDRANT__SERVICE__READ_ONLY_API_KEY': monitor_key}
    try:
        command('docker', 'run', '-d', '--name', name, '--memory', '512m', '--cpus', '1',
            '--mount', f'type=volume,src={volume},dst=/qdrant/storage', '-e', 'QDRANT__SERVICE__API_KEY',
            '-e', 'QDRANT__SERVICE__READ_ONLY_API_KEY', '-e', 'QDRANT__SERVICE__JWT_RBAC=true', '-e', 'QDRANT__TELEMETRY_DISABLED=true',
            '-p', '127.0.0.1::6333', IMAGE, env=env)
        port = int(command('docker', 'port', name, '6333/tcp').rsplit(':', 1)[1])
        endpoint = f'http://127.0.0.1:{port}'
        provider = Qdrant(endpoint, key)
        for _ in range(80):
            try:
                provider.root.request('GET', '/collections')
                break
            except Exception:
                time.sleep(.2)
        else:
            raise AssertionError('Disposable Qdrant not ready')
        first, other = ({'resource_id': str(uuid4()), 'configuration': {'vector_size': 4, 'distance': 'Cosine'}} for _ in range(2))
        for resource in (first, other):
            provider.provision(resource)
            provider.provision(resource)
        credentials = []
        for mode in ('read-write', 'read-only'):
            cred = {'credential_id': str(uuid4()), 'mode': mode,
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            provider.issue(first, cred)
            provider.issue(first, cred)
            provider.probe(first, cred)
            credentials.append(cred)
        from app.stores.native_monitoring import qdrant as native_metrics
        output = native_metrics(provider, [{**first,'state':'active','owner_project':'fixture'}, {**other,'state':'active','owner_project':'other'}])
        assert any('platform_native_qdrant_collection_points' in item for item in output)
        assert any('platform_native_qdrant_memory_resident_bytes' in item for item in output)
        monitor = PrivateJSON(endpoint, {'api-key': monitor_key})
        denied(lambda: monitor.request('PUT', '/collections/not-allowed', {'vectors':{'size':1,'distance':'Dot'}}))
        print('PASS bounded native metrics and read-only monitoring identity write denial')
        writer, reader = credentials
        rw = PrivateJSON(endpoint, {'api-key': provider.token(first, writer)})
        ro = PrivateJSON(endpoint, {'api-key': provider.token(first, reader)})
        prefix = '/collections/' + collection(first)
        foreign = '/collections/' + collection(other)
        rw.request('PUT', prefix + '/points?wait=true', {'points': [
            {'id': 1, 'vector': [1, 0, 0, 0], 'payload': {'kind': 'reviewed', 'source_version': 'fixture-v1'}},
            {'id': 2, 'vector': [0, 1, 0, 0], 'payload': {'kind': 'other', 'source_version': 'fixture-v1'}}]})
        rw.request('PUT', prefix + '/index?wait=true', {'field_name': 'kind', 'field_schema': 'keyword'})
        result = ro.request('POST', prefix + '/points/query', {'query': [1, 0, 0, 0], 'limit': 1,
            'filter': {'must': [{'key': 'kind', 'match': {'value': 'reviewed'}}]}})
        assert result['result']['points'][0]['id'] == 1
        denied(lambda: ro.request('PUT', prefix + '/points?wait=true', {'points': [{'id': 3, 'vector': [0, 0, 1, 0]}]}))
        denied(lambda: ro.request('PUT', prefix + '/index?wait=true', {'field_name': 'secret', 'field_schema': 'keyword'}))
        denied(lambda: rw.request('DELETE', prefix))
        denied(lambda: rw.request('PUT', '/collections/rogue', {'vectors': {'size': 4, 'distance': 'Cosine'}}))
        denied(lambda: rw.request('GET', foreign))
        denied(lambda: rw.request('GET', '/collections/' + VALIDATION))
        denied(lambda: rw.request('PUT', '/collections/' + VALIDATION + '/points?wait=true', {'points': []}))
        # Native listings must also omit resources outside the grant.
        listing = ro.request('GET', '/collections')['result']['collections']
        assert [item['name'] for item in listing] == [collection(first)]
        provider.validate_recovery(first)
        assert provider.usage(first) >= 0
        with restored(name, volume, '/qdrant/storage', IMAGE, ['--memory', '512m', '--cpus', '1',
                '-e', 'QDRANT__SERVICE__API_KEY', '-e', 'QDRANT__SERVICE__READ_ONLY_API_KEY', '-e', 'QDRANT__SERVICE__JWT_RBAC=true',
                '-e', 'QDRANT__TELEMETRY_DISABLED=true', '-p', '127.0.0.1::6333'], env) as recovered_name:
            recovered_port = int(command('docker', 'port', recovered_name, '6333/tcp').rsplit(':', 1)[1])
            recovered = Qdrant(f'http://127.0.0.1:{recovered_port}', key)
            for _ in range(100):
                try:
                    recovered.validate_recovery(first)
                    break
                except Exception:
                    time.sleep(.2)
            else:
                raise AssertionError('Restored Qdrant did not become ready')
            for old in credentials:
                recovered.revoke(first, old)
                denied(lambda c=old: recovered.probe(first, c))
            fresh = {'credential_id': str(uuid4()), 'mode': 'read-only',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            recovered.issue(first, fresh)
            fresh_reader = PrivateJSON(recovered.endpoint, {'api-key': recovered.token(first, fresh)})
            restored_query = fresh_reader.request('POST', prefix + '/points/query',
                {'query': [1, 0, 0, 0], 'limit': 1, 'filter': {'must': [{'key': 'kind', 'match': {'value': 'reviewed'}}]}})
            assert restored_query['result']['points'][0]['id'] == 1
            assert fresh_reader.request('GET', prefix)['result']['payload_schema']['kind']['data_type'] == 'keyword'
            denied(lambda: fresh_reader.request('GET', foreign))
            recovered.validate_recovery(other)
        print('PASS Qdrant stopped-volume capture and empty-volume restore: vectors/payload indexes/validation records retained; recovered keys revoked; fresh scoped query succeeds')
        port = int(command('docker', 'port', name, '6333/tcp').rsplit(':', 1)[1])
        endpoint = f'http://127.0.0.1:{port}'
        provider = Qdrant(endpoint, key)
        for _ in range(100):
            try:
                provider.validate_recovery(first)
                break
            except Exception:
                time.sleep(.2)
        else:
            raise AssertionError('Original Qdrant did not recover after capture')

        async def relay_access():
            lease = {**reader, 'resource_id': first['resource_id'], 'provider': 'qdrant',
                'expires_at': datetime.now(timezone.utc) + timedelta(seconds=.8)}
            relay = Relay(backend=lambda lease: ('127.0.0.1', port))
            relay.leases = {20000: lease}
            relay.last_success = time.monotonic()
            server = await asyncio.start_server(lambda r, w: relay.handle(20000, r, w), '127.0.0.1', 0)
            try:
                async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}',
                        headers={'api-key': provider.token(first, reader)}, timeout=2) as http:
                    assert (await http.get(prefix)).status_code == 200
                    await asyncio.sleep(.9)
                    try:
                        await http.get(prefix)
                    except httpx.TransportError:
                        pass
                    else:
                        raise AssertionError('Expired Qdrant relay lease accepted another request')
            finally:
                relay.leases.clear()
                server.close()
                await server.wait_closed()
        asyncio.run(relay_access())
        expired = {'credential_id': str(uuid4()), 'mode': 'read-only',
            'expires_at': (datetime.now(timezone.utc) - timedelta(seconds=40)).isoformat()}
        provider.issue(first, expired)
        denied(lambda: provider.probe(first, expired))
        for credential in [*credentials, expired]:
            provider.revoke(first, credential)
            provider.revoke(first, credential)
            denied(lambda c=credential: provider.probe(first, c))
        provider.purge(first)
        provider.purge(first)
        provider.validate_recovery(other)
        print('PASS pinned Qdrant: exact collection JWT RBAC, reader/writer/payload schema, filtered retrieval, foreign and validation-collection denial, native revocation/expiry, strict relay expiry, measured disk usage and isolated purge')
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
