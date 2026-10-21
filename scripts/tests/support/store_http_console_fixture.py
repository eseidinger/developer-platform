"""Native HTTP-store console/browser fixture, called by the Compose fixture.

The browser uses real TLS to a disposable loopback gateway through a bounded
CONNECT proxy, preserving the public origin/Host. Its synthetic certificate is
fixture-only; public DNS, trusted-certificate and deployed OIDC acceptance remain open.
Only synthetic credentials travel over stdin/in memory; no browser artifacts.
"""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import contextlib
import tempfile
from datetime import datetime, timedelta, timezone
import json
import os
import secrets
import socket
import subprocess
import time
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from starlette.routing import Host
from app.stores import catalog, console
from app.stores.relay import Relay
from app.stores.qdrant import collection

ROOT = Path(__file__).resolve().parents[3]


async def run(providers, endpoints, static_ports):
    # Keep normal CI aligned with supported runtime adapters. Pending provider
    # experiments remain explicit, disposable and separate from acceptance.
    if os.environ.get('STORE_CONSOLE_VERIFY_PENDING') != '1':
        providers = {name: provider for name, provider in providers.items() if name in console.PROVIDERS}
    os.environ.update({'DATABASE_KEY': secrets.token_hex(32), 'STORE_CONSOLE_HTTP_ENABLED': 'true',
        'STORE_ENABLED_PROVIDERS': 's3,qdrant,opensearch,neo4j', 'STORE_RELAY_IP':'127.0.0.1', 'APPS_DOMAIN': 'apps.fixture.test',
        'PLATFORM_DOMAIN': 'platform.fixture.test', 'PROXY_IP': '127.0.0.1'})
    rows, resources, credentials, issued = {}, {}, {}, {}
    variants = [(name, provider, mode) for name, provider in providers.items()
                for mode in (('read-write','second-read-write') if name == 'neo4j' else ('read-write','read-only'))]
    if 'opensearch' in providers:
        variants.append(('opensearch', providers['opensearch'], 'renewed-read-only'))
    for index, (name, provider, selected_mode) in enumerate(variants):
        variant = name + '-' + selected_mode
        mode = selected_mode.removeprefix('renewed-').removeprefix('second-')
        resource = resources['opensearch-read-write'] if selected_mode == 'renewed-read-only' else {
            'resource_id': str(uuid4()), 'quota_bytes': 16 * 1024 * 1024,
            'configuration': {'vector_size': 3, 'distance': 'Cosine'}}
        for attempt in range(100):
            try:
                await asyncio.to_thread(provider.provision, resource)
                break
            except Exception:
                if attempt == 99: raise
                await asyncio.sleep(.25)
        credential = {'credential_id': str(uuid4()), 'mode': mode, 'kind': 'human',
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
        await asyncio.to_thread(provider.issue, resource, credential)
        row = {**credential, 'expires_at': datetime.fromisoformat(credential['expires_at']),
               'relay_port': 20000 + index, 'issuer': 'https://identity.fixture.test', 'subject': 'human',
               'provider': name, 'fixture_variant': variant, 'resource_id': resource['resource_id'], 'created_at': datetime.now(timezone.utc), 's3_sessions': {}}
        if name == 'neo4j':
            import hashlib
            instance = await asyncio.to_thread(provider.provision, resource)
            row.update(native_host=instance['host'], admission_sha256=hashlib.sha256(catalog.secret_for(credential['credential_id']).encode()).hexdigest())
        rows[row['relay_port']] = row
        resources[variant] = resource
        credentials[variant] = provider.credentials(resource, credential)
        issued[variant] = (provider, resource, credential)
        if name == 's3':
            from app.stores.s3 import bucket
            await asyncio.to_thread(provider.root.put_object, Bucket=bucket(resource), Key='fixture.txt', Body=b'console fixture')
        if name == 'opensearch':
            from app.stores.opensearch import index
            await asyncio.to_thread(provider.root.request, 'PUT', '/' + index(resource) + '/_doc/fixture?refresh=true', {'title': 'console fixture', 'kind': 'scoped'})
    relay = Relay(load=lambda: {port: {**row, 's3_sessions': dict(row['s3_sessions'])} for port, row in rows.items()}, backend=lambda row: (row['native_host'],7687) if row['provider']=='neo4j' else ('127.0.0.1', endpoints[row['provider']]), host='127.0.0.1')
    async def refresh():
        while True:
            await relay.refresh()
            await asyncio.sleep(.1)
    refreshing = asyncio.create_task(refresh())
    def load(cid):
        return next((r for r in rows.values() if r['credential_id'] == str(cid)
            and r['expires_at'] > datetime.now(timezone.utc)), None)
    def register(row, access, digest, expiry):
        assert load(row['credential_id']) is not None
        rows[row['relay_port']]['s3_sessions'][access] = {'token_sha256': digest, 'expires_at': expiry}
    health = await asyncio.start_server(relay.health, '127.0.0.1', 0)
    async def acknowledge(row, access, digest):
        import httpx2 as httpx
        url = f'http://127.0.0.1:{health.sockets[0].getsockname()[1]}/session/{row["relay_port"]}/{access}/{digest}'
        async with httpx.AsyncClient(trust_env=False) as transport:
            for _ in range(50):
                if (await transport.get(url)).status_code == 200: return
                await asyncio.sleep(.1)
        raise RuntimeError('Relay did not observe the console child session')
    app = FastAPI()
    app.router.routes.append(Host('console-{port:int}.apps.fixture.test', app=console.create_gateway(load,
        destination=lambda row, static: (row['native_host'],7474) if row['provider']=='neo4j' else ('127.0.0.1', static_ports[row['provider']] if static or row['provider'] == 'opensearch' else row['relay_port']),
        register=register, acknowledge=acknowledge)))
    @app.post('/expire/{port}')
    def expire(port: int):
        rows[port]['expires_at'] = datetime.now(timezone.utc) + timedelta(milliseconds=200)
        return {}
    @app.post('/revoke/{port}')
    def revoke(port: int):
        rows.pop(port, None)
        return {}
    @app.post('/launch/{port}')
    def fresh_launch(port: int):
        return {'launch': console.assertion(rows[port], 'launch', 30)}
    @app.get('/ping')
    def ping(): return {}
    server_socket = socket.socket(); server_socket.bind(('127.0.0.1', 0))
    gateway_port = server_socket.getsockname()[1]
    directory = tempfile.TemporaryDirectory(prefix='store-console-tls-')
    private = Path(directory.name)
    result = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=console.apps.fixture.test', '-keyout', str(private / 'key.pem'), '-out', str(private / 'cert.pem')],
        capture_output=True, timeout=15)
    if result.returncode: raise RuntimeError('Fixture certificate preparation failed')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=gateway_port, log_level='critical', access_log=False,
        ssl_certfile=str(private / 'cert.pem'), ssl_keyfile=str(private / 'key.pem')))
    lease_ports = tuple(rows)
    async def tunnel(reader, writer):
        upstream = None
        tasks = []
        try:
            packet = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 3)
            line = packet.split(b'\r\n', 1)[0]
            allowed = [f'CONNECT console-{port}.apps.fixture.test:443 HTTP/1.1'.encode() for port in lease_ports]
            allowed.append(f'CONNECT 127.0.0.1:{gateway_port} HTTP/1.1'.encode())
            if line not in allowed or len(packet) > 8192: return
            remote, upstream = await asyncio.open_connection('127.0.0.1', gateway_port)
            writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n'); await writer.drain()
            async def copy(source, target):
                while value := await source.read(65536): target.write(value); await target.drain()
            tasks = [asyncio.create_task(copy(reader, upstream)), asyncio.create_task(copy(remote, writer))]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except Exception: pass
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in (upstream, writer):
                if stream is not None:
                    stream.close()
                    with contextlib.suppress(Exception): await stream.wait_closed()
    proxy = await asyncio.start_server(tunnel, '127.0.0.1', 0)
    proxy_port = proxy.sockets[0].getsockname()[1]
    running = asyncio.create_task(server.serve(sockets=[server_socket]))
    stack = contextlib.AsyncExitStack()
    try:
        if 'opensearch' in providers:
            from scripts.tests.support.store_dashboards_fixture import running as running_dashboards
            resource = next(row for row in rows.values() if row['provider'] == 'opensearch')
            static_ports['opensearch'] = await stack.enter_async_context(running_dashboards(load, providers['opensearch'], resource))
        for _ in range(100):
            if server.started and len(relay.servers) == len(rows): break
            await asyncio.sleep(.05)
        else: raise RuntimeError('Disposable console gateway did not start')
        config = {'gateway': f'https://127.0.0.1:{gateway_port}', 'proxy': f'http://127.0.0.1:{proxy_port}', 'providers': {}}
        for port, row in rows.items():
            variant = row['fixture_variant']
            other = row['provider'] + '-' + ('read-only' if row['mode'] == 'read-write' else 'read-write')
            if row['provider'] == 'neo4j': other = 'neo4j-' + ('second-read-write' if variant == 'neo4j-read-write' else 'read-write')
            if 'renewed-' in variant: other = 'opensearch-read-only'
            config['providers'][variant] = {'origin': console.origin(port), 'provider': row['provider'], 'mode': row['mode'], 'retained_workspace': 'renewed-' in variant, 'peer': credentials[other],
                'foreign': credentials[other].get('S3_BUCKET', credentials[other].get('QDRANT_COLLECTION', credentials[other].get('OPENSEARCH_INDEX'))),
                'launch': console.assertion(row, 'launch', 30), 'port': port,
                'connection': credentials[variant]}
        try:
            result = await asyncio.to_thread(subprocess.run, ['node', str(ROOT / 'platform/ui/scripts/verify-http-store-consoles.mjs')],
            input=json.dumps(config), text=True, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b''
            if isinstance(output, bytes): output = output.decode(errors='replace')
            raise RuntimeError('Synthetic console fixture timed out at: ' + output[-2000:]) from None
        if result.returncode:
            if 'opensearch' in providers:
                native = providers['opensearch']
                for physical, _ in native.console_indices(resources['opensearch-read-write']):
                    mapping = await asyncio.to_thread(native.root.request, 'GET', '/' + physical + '/_mapping')
                    properties = mapping[physical]['mappings'].get('properties', {})
                    print('Synthetic saved-object mapping types: ' + json.dumps({key: properties.get(key, {}).get('type')
                        for key in ('type', 'namespaces', 'namespace', 'updated_at')}))
            raise RuntimeError('Official console fixture failed: ' + result.stdout.strip()[:1200])
        # Native 24-hour keys remain valid: the previous denials must come from
        # the authoritative lease boundary, not native deletion or fixture routing.
        for provider, resource, credential in issued.values():
            await asyncio.to_thread(provider.probe, resource, credential)
        print(result.stdout.strip())
        if 'opensearch' in providers:
            provider = providers['opensearch']
            first, other = resources['opensearch-read-write'], resources['opensearch-read-only']
            assert provider.console_indices(first) and provider.console_indices(other)
            for variant, (native, resource, credential) in issued.items():
                if variant.startswith('opensearch') and resource['resource_id'] == first['resource_id']:
                    await asyncio.to_thread(native.revoke, resource, credential)
            await asyncio.to_thread(provider.purge, first)
            await asyncio.to_thread(provider.purge, first)
            assert not provider.console_indices(first) and provider.console_indices(other)
            await asyncio.to_thread(provider.validate_recovery, other)
            print('PASS resource workspace survives human renewal; isolated idempotent purge removes its data, tenant and physical console indexes while retaining the other workspace')
    finally:
        await stack.aclose()
        server.should_exit = True
        await running
        proxy.close(); await proxy.wait_closed()
        health.close(); await health.wait_closed()
        directory.cleanup()
        refreshing.cancel()
        await asyncio.gather(refreshing, return_exceptions=True)
        relay.leases = {}
        for listening in relay.servers.values(): listening.close(); await listening.wait_closed()
