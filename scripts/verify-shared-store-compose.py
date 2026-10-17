#!/usr/bin/env python3
"""Temporary provider-only Compose fixture using the actual production services.

No platform, cluster, public ports, real installation or external notification is
created. Every volume/network belongs to this unique, cleaned-up fixture project.
"""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from uuid import uuid4

import yaml
from app.stores.s3 import S3
from app.stores.qdrant import Qdrant
from app.stores.opensearch import OpenSearch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compose_store_prepare', ROOT / 'scripts/prepare-stores.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


def main():
    project = 'store-compose-' + uuid4().hex[:12]
    config = {'COMPOSE_PROFILES': 's3,qdrant,opensearch', 'OPENSEARCH_IP': '127.0.0.1',
        'RUSTFS_ACCESS_KEY': secrets.token_hex(10), 'RUSTFS_SECRET_KEY': secrets.token_hex(32),
        'QDRANT_API_KEY': secrets.token_hex(32), 'OPENSEARCH_ADMIN_PASSWORD': secrets.token_hex(32),
        'OPENSEARCH_DASHBOARDS_PASSWORD': secrets.token_hex(32)}
    consoles = os.environ.get('STORE_CONSOLE_FIXTURE') == '1'
    if consoles: config['COMPOSE_PROFILES'] = 's3,qdrant'
    env = {**os.environ, **config}
    with tempfile.TemporaryDirectory(prefix='shared-store-compose-') as directory:
        path = Path(directory)
        preparation.prepare(path / 'stores', config)
        data = copy.deepcopy(yaml.safe_load((ROOT / 'persistence/shared-stores.yaml').read_text()))
        if consoles:
            del data['services']['opensearch']; del data['services']['opensearch-init']
        for service, value in data['services'].items():
            value['networks'] = {'fixture': {}}
            mounts = []
            for mount in value.get('volumes', []):
                mount = mount.replace('../.runtime/stores/', str(path / 'stores') + '/')
                if mount.startswith('./opensearch-bootstrap.sh:'):
                    mount = mount.replace('./opensearch-bootstrap.sh', str(ROOT / 'persistence/opensearch-bootstrap.sh'), 1)
                mounts.append(mount)
            value['volumes'] = mounts
            port = {'rustfs': 9000, 'qdrant': 6333, 'opensearch': 9200}.get(service)
            if port:
                value['ports'] = [f'127.0.0.1::{port}']
                if service == 'rustfs': value['ports'].append('127.0.0.1::9001')
        data['networks'] = {'fixture': {}}
        data['volumes'] = {name: {} for name in ('rustfs_data', 'qdrant_data', 'opensearch_data')}
        file = path / 'compose.yaml'; file.write_text(yaml.safe_dump(data, sort_keys=False)); file.chmod(0o600)
        base = ['docker', 'compose', '-p', project, '-f', str(file)]

        def command(arguments, timeout=60):
            result = subprocess.run(arguments, env=env, capture_output=True, timeout=timeout)
            if result.returncode:
                raise RuntimeError('Temporary shared-store Compose operation failed')
            return result.stdout.decode().strip()

        try:
            command([*base, 'up', '-d', '--wait', '--wait-timeout', '180'], timeout=240)
            for service in (('rustfs', 'qdrant') if consoles else ('rustfs', 'qdrant', 'opensearch')):
                identity = command([*base, 'ps', '-q', service])
                state = json.loads(command(['docker', 'inspect', '--format', '{{json .State}}', identity]))
                assert state['Running'] and state['Health']['Status'] == 'healthy', service
            if not consoles:
                initialized = command([*base, 'ps', '-aq', 'opensearch-init'])
                assert command(['docker', 'inspect', '--format', '{{.State.ExitCode}}', initialized]) == '0'
            def endpoint(service, port, scheme='http'):
                address = command([*base, 'port', service, str(port)])
                return f'{scheme}://127.0.0.1:' + address.rsplit(':', 1)[1]
            S3(endpoint('rustfs', 9000), config['RUSTFS_ACCESS_KEY'], config['RUSTFS_SECRET_KEY']).root.list_buckets()
            Qdrant(endpoint('qdrant', 6333), config['QDRANT_API_KEY']).root.request('GET', '/collections')
            if not consoles:
                OpenSearch(endpoint('opensearch', 9200, 'https'), config['OPENSEARCH_ADMIN_PASSWORD'],
                    str(path / 'stores/public/opensearch-ca.pem')).root.request('GET', '/_cluster/health')
            if consoles:
                from store_http_console_fixture import run as verify_consoles
                asyncio.run(verify_consoles({'s3': S3(endpoint('rustfs', 9000), config['RUSTFS_ACCESS_KEY'], config['RUSTFS_SECRET_KEY']),
                    'qdrant': Qdrant(endpoint('qdrant', 6333), config['QDRANT_API_KEY'])},
                    {'s3': int(endpoint('rustfs', 9000).rsplit(':', 1)[1]), 'qdrant': int(endpoint('qdrant', 6333).rsplit(':', 1)[1])},
                    {'s3': int(endpoint('rustfs', 9001).rsplit(':', 1)[1]), 'qdrant': int(endpoint('qdrant', 6333).rsplit(':', 1)[1])}))
            print('PASS selected production Compose services: persistent volumes, resource limits, actual health checks and native administration; provider-only disposable fixture')
        except Exception:
            # Installation diagnostics contain no plaintext secrets in these
            # synthetic services. Only service names/state are printed here.
            result = subprocess.run([*base, 'ps', '-a', '--format', '{{.Service}} {{.State}} {{.Health}}'],
                env=env, capture_output=True, text=True, timeout=10)
            print(result.stdout)
            raise
        finally:
            subprocess.run([*base, 'down', '--volumes', '--remove-orphans', '--timeout', '20'],
                env=env, capture_output=True, timeout=90)


if __name__ == '__main__':
    main()
