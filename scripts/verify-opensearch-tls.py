#!/usr/bin/env python3
"""Exercise the actual generated TLS and idempotent non-demo realm initializer."""
import importlib.util
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from app.stores.opensearch import OpenSearch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('store_prepare', ROOT / 'scripts/prepare-stores.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


def command(*arguments):
    result = subprocess.run(arguments, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError('Disposable native TLS/initialization operation failed')
    return result.stdout.decode().strip()


def main():
    name = 'search-tls-' + uuid4().hex[:12]
    password = 'Aa9!' + secrets.token_hex(32)
    os.environ['DATABASE_KEY'] = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix='opensearch-native-tls-') as directory:
        root = Path(directory)
        preparation.prepare(root, {'COMPOSE_PROFILES': 'opensearch', 'OPENSEARCH_IP': '127.0.0.1',
            'OPENSEARCH_ADMIN_PASSWORD': password, 'OPENSEARCH_DASHBOARDS_PASSWORD': secrets.token_hex(32)})
        private = root / 'opensearch'
        original_ca = (private / 'ca.pem').read_bytes()
        preparation.prepare(root, {'COMPOSE_PROFILES': 'opensearch', 'OPENSEARCH_IP': '127.0.0.1'})
        assert (private / 'ca.pem').read_bytes() == original_ca
        mounts = []
        for filename in ('ca.pem', 'node.pem', 'node-key.pem', 'opensearch.yml'):
            mounts += ['-v', f'{private / filename}:/usr/share/opensearch/config/{filename}:ro']
        try:
            command('docker', 'run', '-d', '--name', name, '--hostname', 'opensearch', '--memory', '1536m',
                '--cpus', '1', '--tmpfs', '/usr/share/opensearch/data:rw,uid=1000,gid=1000,size=128m',
                '-e', 'DISABLE_INSTALL_DEMO_CONFIG=true', '-e', 'OPENSEARCH_JAVA_OPTS=-Xms256m -Xmx256m',
                '-p', '127.0.0.1::9200', *mounts, preparation.IMAGE)
            initializer = ['docker', 'run', '--name', name + '-init', '--user', '1000:1000', '--cap-drop', 'ALL', '--memory', '512m', '--cpus', '1',
                '--network', 'container:' + name, '-e', 'OPENSEARCH_HOST=127.0.0.1',
                '-v', f'{private / "ca.pem"}:/run/store-security/ca.pem:ro',
                '-v', f'{private / "admin.pem"}:/run/store-security/admin.pem:ro',
                '-v', f'{private / "admin-key.pem"}:/run/store-security/admin-key.pem:ro',
                '-v', f'{private / "bootstrap"}:/run/store-security/bootstrap:ro', '-v',
                f'{ROOT / "persistence/opensearch-bootstrap.sh"}:/bootstrap.sh:ro', '--entrypoint', 'bash', preparation.IMAGE, '/bootstrap.sh']
            command(*initializer)
            port = int(command('docker', 'port', name, '9200/tcp').rsplit(':', 1)[1])
            provider = OpenSearch(f'https://127.0.0.1:{port}', password, str(private / 'ca.pem'))
            for _ in range(80):
                try:
                    provider.root.request('GET', '/_cluster/health')
                    break
                except Exception:
                    time.sleep(.25)
            else:
                raise AssertionError('Native TLS store did not become healthy')
            resource = {'resource_id': str(uuid4())}
            credential = {'credential_id': str(uuid4()), 'mode': 'read-write',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            provider.provision(resource)
            provider.issue(resource, credential)
            provider.probe(resource, credential)
            # Existing native users/roles/data must survive a second deployment.
            command('docker', 'rm', '-f', '-v', name + '-init')
            output = command(*initializer)
            assert 'already initialized; retained' in output
            provider.probe(resource, credential)
            print('PASS generated operator CA/server/admin TLS, verified hostname, non-demo native realm initialization, exact resource roles, repeat preparation and retained users on second initialization')
        except Exception:
            result = subprocess.run(['docker', 'logs', '--tail', '35', name], capture_output=True, text=True, timeout=5)
            print(result.stdout + result.stderr)
            result = subprocess.run(['docker', 'logs', name + '-init'], capture_output=True, text=True, timeout=5)
            print(result.stdout + result.stderr)
            diagnostic = root / 'init.log'
            copied = subprocess.run(['docker', 'cp', name + '-init:/tmp/security-init.log', str(diagnostic)], capture_output=True, timeout=5)
            if copied.returncode == 0:
                print('\n'.join(diagnostic.read_text().splitlines()[-24:]))
            raise
        finally:
            subprocess.run(['docker', 'rm', '-f', '-v', name + '-init'], capture_output=True, timeout=30)
            subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
