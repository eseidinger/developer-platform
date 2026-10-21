#!/usr/bin/env python3
"""Temporary provider-only Compose fixture using the actual production services.

No platform, cluster, public ports, real installation or external notification is
created. Every volume/network belongs to this unique, cleaned-up fixture project.
"""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import copy
import importlib.util
import json
import os
import secrets
import subprocess
import tempfile
from uuid import uuid4

import yaml
from app.stores.s3 import S3
from app.stores.qdrant import Qdrant
from app.stores.opensearch import OpenSearch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('compose_store_prepare', ROOT / 'scripts/setup/prepare-stores.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


def main():
    project = 'store-compose-' + uuid4().hex[:12]
    config = {'COMPOSE_PROFILES': 's3,qdrant,opensearch', 'OPENSEARCH_IP': '127.0.0.1',
        'RUSTFS_ACCESS_KEY': secrets.token_hex(10), 'RUSTFS_SECRET_KEY': secrets.token_hex(32),
        'QDRANT_API_KEY': secrets.token_hex(32), 'OPENSEARCH_ADMIN_PASSWORD': secrets.token_hex(32),
        'OPENSEARCH_DASHBOARDS_PASSWORD': secrets.token_hex(32), 'STORE_OPENSEARCH_CONSOLE_COOKIE_KEY': secrets.token_hex(32)}
    dashboards = os.environ.get('STORE_DASHBOARDS_FIXTURE') == '1'
    consoles = os.environ.get('STORE_CONSOLE_FIXTURE') == '1' or dashboards
    if consoles: config['COMPOSE_PROFILES'] = 'opensearch' if dashboards else 's3,qdrant'
    env = {**os.environ, **config}
    with tempfile.TemporaryDirectory(prefix='shared-store-compose-') as directory:
        path = Path(directory)
        preparation.prepare(path / 'stores', config)
        data = copy.deepcopy(yaml.safe_load((ROOT / 'infrastructure/persistence/shared-stores.yaml').read_text()))
        del data['services']['neo4j-controller']  # Dedicated-controller fixtures run separately, without live infrastructure membership.
        del data['services']['opensearch-dashboards']  # Browser fixture supplies its private bridge.
        selected = ('opensearch', 'opensearch-init') if dashboards else (('rustfs', 'qdrant') if consoles else tuple(data['services']))
        data['services'] = {name: value for name, value in data['services'].items() if name in selected}
        for service, value in data['services'].items():
            value['networks'] = {'fixture': {}}
            mounts = []
            for mount in value.get('volumes', []):
                mount = mount.replace('../.runtime/stores/', str(path / 'stores') + '/')
                if mount.startswith('./opensearch-bootstrap.sh:'):
                    mount = mount.replace('./opensearch-bootstrap.sh', str(ROOT / 'infrastructure/persistence/opensearch-bootstrap.sh'), 1)
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
            for service in (name for name in data['services'] if name != 'opensearch-init'):
                identity = command([*base, 'ps', '-q', service])
                state = json.loads(command(['docker', 'inspect', '--format', '{{json .State}}', identity]))
                assert state['Running'] and state['Health']['Status'] == 'healthy', service
            if 'opensearch' in data['services']:
                initialized = command([*base, 'ps', '-aq', 'opensearch-init'])
                assert command(['docker', 'inspect', '--format', '{{.State.ExitCode}}', initialized]) == '0'
            def endpoint(service, port, scheme='http'):
                address = command([*base, 'port', service, str(port)])
                return f'{scheme}://127.0.0.1:' + address.rsplit(':', 1)[1]
            providers, native_ports, static_ports = {}, {}, {}
            if 'rustfs' in data['services']:
                providers['s3'] = S3(endpoint('rustfs', 9000), config['RUSTFS_ACCESS_KEY'], config['RUSTFS_SECRET_KEY'])
                providers['s3'].root.list_buckets()
                native_ports['s3'] = int(endpoint('rustfs', 9000).rsplit(':', 1)[1])
                static_ports['s3'] = int(endpoint('rustfs', 9001).rsplit(':', 1)[1])
            if 'qdrant' in data['services']:
                providers['qdrant'] = Qdrant(endpoint('qdrant', 6333), config['QDRANT_API_KEY'])
                providers['qdrant'].root.request('GET', '/collections')
                native_ports['qdrant'] = static_ports['qdrant'] = int(endpoint('qdrant', 6333).rsplit(':', 1)[1])
            if 'opensearch' in data['services']:
                providers['opensearch'] = OpenSearch(endpoint('opensearch', 9200, 'https'), config['OPENSEARCH_ADMIN_PASSWORD'],
                    str(path / 'stores/public/opensearch-ca.pem'))
                providers['opensearch'].root.request('GET', '/_cluster/health')
                native_ports['opensearch'] = int(endpoint('opensearch', 9200, 'https').rsplit(':', 1)[1])
            if consoles:
                from scripts.fixtures.store_http_console_fixture import run as verify_consoles
                os.environ['OPENSEARCH_DASHBOARDS_PASSWORD'] = config['OPENSEARCH_DASHBOARDS_PASSWORD']
                if dashboards:
                    native_id = command([*base, 'ps', '-q', 'opensearch'])
                    networks = json.loads(command(['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}', native_id]))
                    native_network, native_address = next(iter(networks.items()))
                    os.environ['STORE_FIXTURE_OPENSEARCH_RAW_NETWORK'] = native_network
                    os.environ['STORE_FIXTURE_OPENSEARCH_RAW_IP'] = native_address['IPAddress']
                asyncio.run(verify_consoles(providers, native_ports, static_ports))
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
