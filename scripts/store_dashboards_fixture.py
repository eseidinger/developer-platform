"""Disposable official Dashboards process, private native bridge and real TLS upstream."""
import asyncio
import base64
from collections import Counter
from contextlib import asynccontextmanager
import copy
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
from uuid import uuid4

import httpx2 as httpx
import uvicorn
import yaml
from fastapi import FastAPI
from starlette.routing import Host
from app.stores import dashboards

ROOT = Path(__file__).resolve().parents[1]


async def isolation(image, name):
    """Positive/negative TCP controls against the same real native listener."""
    native_network = os.environ['STORE_FIXTURE_OPENSEARCH_RAW_NETWORK']
    native_address = os.environ['STORE_FIXTURE_OPENSEARCH_RAW_IP']
    config = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    assert config['networks']['search-consoles']['internal'] is True
    service = yaml.safe_load((ROOT / 'persistence/shared-stores.yaml').read_text())['services']['opensearch-dashboards']
    assert set(service['networks']) == {'search-consoles'} and not service.get('ports')
    result = await asyncio.to_thread(subprocess.run, ['docker', 'network', 'create', '--internal', name], capture_output=True, timeout=15)
    if result.returncode: raise RuntimeError('Disposable isolated console network did not start')
    try:
        for network, expected in ((native_network, 'true'), (name, 'false')):
            code = "const n=require('net');const s=n.connect(9200,process.argv[1]);const done=v=>{s.destroy();process.exit(v===process.argv[2]?0:1)};s.once('connect',()=>done('true'));s.once('error',()=>done('false'));s.setTimeout(2000,()=>done('false'))"
            result = await asyncio.to_thread(subprocess.run, ['docker', 'run', '--rm', '--network', network,
                '--cap-drop', 'ALL', '--entrypoint', '/usr/share/opensearch-dashboards/node/bin/node', image,
                '-e', code, native_address, expected], capture_output=True, timeout=15)
            if result.returncode: raise RuntimeError('Console network native-bypass control failed')
        print('PASS isolated console network denies raw OpenSearch TCP; positive control reaches the same native listener')
    finally:
        await asyncio.to_thread(subprocess.run, ['docker', 'network', 'rm', name], capture_output=True, timeout=15)


@asynccontextmanager
async def running(load, provider, resource):
    os.environ.update({'OPENSEARCH_DASHBOARDS_IP': '127.0.0.1', 'OPENSEARCH_IP': '127.0.0.1',
        'OPENSEARCH_CA_FILE': provider.ca_file, 'STORE_RELAY_IP': '127.0.0.1'})
    app = FastAPI()
    statuses = Counter()
    @app.middleware('http')
    async def observed(request, call_next):
        result = await call_next(request)
        category = ('authinfo' if request.url.path == '/_plugins/_security/authinfo' else
            'dashboardsinfo' if request.url.path == '/_plugins/_security/dashboardsinfo' else
            'aliases' if '_alias' in request.url.path else 'cat-indices' if '/_cat/indices' in request.url.path else
            'field-caps' if '_field_caps' in request.url.path else 'resolve-index' if '/_resolve/index' in request.url.path else 'other')
        try:
            principal = base64.b64decode(request.headers.get('authorization', '').removeprefix('Basic ')).split(b':')[0]
            principal = 'server' if principal == b'kibanaserver' else 'user' if principal.startswith(b'credential_') else 'none'
        except Exception: principal = 'invalid'
        statuses[category + ':' + request.method + ':' + principal + (':bound' if dashboards.HEADER in request.headers else ':unbound')
            + (':tenant' if request.headers.get('securitytenant') else ':no-tenant') + ':' + str(result.status_code)] += 1
        return result
    app.router.routes.append(Host(dashboards.HOST,
        app=dashboards.create_backend(load, server=(provider.endpoint, provider.ca_file))))
    bound = socket.socket(); bound.bind(('127.0.0.1', 0))
    native_port = bound.getsockname()[1]
    config = uvicorn.Config(app, log_level='critical', access_log=False)
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve(sockets=[bound]))
    name = 'store-dashboards-' + uuid4().hex[:12]
    try:
        for _ in range(100):
            if server.started: break
            await asyncio.sleep(.05)
        else: raise RuntimeError('Disposable native bridge did not start')
        from app.stores.opensearch import authorization, index
        headers = {'Host': dashboards.HOST, 'Authorization': authorization('kibanaserver', os.environ['OPENSEARCH_DASHBOARDS_PASSWORD'])}
        async with httpx.AsyncClient(trust_env=False, timeout=5) as transport:
            for path in ('/' + index(resource) + '/_search', '/_plugins/_security/api/internalusers'):
                result = await transport.get(f'http://127.0.0.1:{native_port}' + path, headers=headers)
                assert result.status_code == 403, 'Console server account exceeded its system metadata role'
        print('PASS restricted console server account cannot read resource documents or administer native identities')
        with tempfile.TemporaryDirectory(prefix='store-dashboards-') as directory:
            source = yaml.safe_load((ROOT / 'persistence/shared-stores.yaml').read_text())
            service = copy.deepcopy(source['services']['opensearch-dashboards'])
            await isolation(service['image'], name + '-isolated')
            settings = yaml.safe_load((ROOT / 'persistence/opensearch-dashboards.yaml').read_text())
            port_socket = socket.socket(); port_socket.bind(('127.0.0.1', 0))
            port = port_socket.getsockname()[1]; port_socket.close()
            settings.update({'server.host': '127.0.0.1', 'server.port': port})
            file = Path(directory) / 'config.yml'; file.write_text(yaml.safe_dump(settings)); file.chmod(0o644)
            env = {**os.environ, 'STORE_OPENSEARCH_BACKEND_URL': f'http://127.0.0.1:{native_port}',
                'OPENSEARCH_DASHBOARDS_PASSWORD': os.environ['OPENSEARCH_DASHBOARDS_PASSWORD'],
                'STORE_OPENSEARCH_CONSOLE_COOKIE_KEY': secrets.token_hex(32)}
            arguments = ['docker', 'run', '-d', '--name', name, '--network', 'host', '--memory', '1g', '--cpus', '1',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--mount', f'type=bind,src={file},dst=/usr/share/opensearch-dashboards/config/opensearch_dashboards.yml,readonly']
            for key in service['environment']: arguments.extend(['-e', key])
            result = await asyncio.to_thread(subprocess.run, [*arguments, service['image']], env=env, capture_output=True, timeout=30)
            if result.returncode: raise RuntimeError('Disposable Dashboards did not start')
            async with httpx.AsyncClient(trust_env=False, timeout=2) as transport:
                for _ in range(240):
                    try:
                        if (await transport.get(f'http://127.0.0.1:{port}/app/login')).status_code == 200: break
                    except httpx.HTTPError: pass
                    await asyncio.sleep(.5)
                else: raise RuntimeError('Disposable Dashboards native login did not become ready')
            yield port
    finally:
        print('Native bridge status counts: ' + json.dumps(dict(statuses), sort_keys=True))
        await asyncio.to_thread(subprocess.run, ['docker', 'rm', '-f', name], capture_output=True, timeout=30)
        server.should_exit = True
        await serving
