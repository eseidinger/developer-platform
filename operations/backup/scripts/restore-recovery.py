#!/usr/bin/env python3
"""Restore a verified bundle on an empty recovery host; invoked by Ansible."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path('/opt/developer-platform')


def run(args, cwd=None, data=None, timeout=300):
    result = subprocess.run(args, cwd=cwd, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed: ' + args[0] + '; inspect private restore logs')
    return result.stdout


def extract(archive, target):
    with tarfile.open(archive) as stream:
        stream.extractall(target, filter='data')


def verify(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    required = {'postgres.sql.gz', 'platform-files.tar.gz', 'proxy-data.tar.gz',
                'proxy-config.tar.gz', 'grafana-grafana.tar.gz', 'versions.json'}
    if manifest.get('format') != 1 or not required <= manifest.get('sha256', {}).keys():
        raise RuntimeError('Incomplete recovery bundle')
    for name, checksum in manifest['sha256'].items():
        path = bundle / name
        if Path(name).name != name or not path.is_file() or path.is_symlink():
            raise RuntimeError('Unsafe bundle file')
        with path.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != checksum:
                raise RuntimeError('Bundle checksum mismatch')
    return manifest


def restore_project_secrets(bundle, name):
    """Recreate one project's app-secrets from the bundle and restart its pods; values go via stdin only."""
    path = bundle / 'project-secrets.json'
    if not path.is_file():
        return False
    stored = json.loads(path.read_text()).get('projects', {}).get(name)
    if not stored:
        return False
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
              'metadata': {'name': 'app-secrets', 'namespace': 'project-' + name,
                           'labels': {'platform.example/managed': 'true'},
                           'annotations': stored.get('annotations') or {}},
              'data': stored['data']}
    kubectl = [str(ROOT / '.runtime/bin/kubectl'), '--kubeconfig', str(ROOT / '.runtime/admin.kubeconfig')]
    run(kubectl + ['apply', '--server-side', '--force-conflicts', '--field-manager', 'platform-recovery',
                   '-f', '-'], data=json.dumps(secret).encode())
    run(kubectl + ['-n', 'project-' + name, 'rollout', 'restart', 'deployment/' + name])
    return True


def check_import_errors(stderr):
    # pg_dumpall meets the two objects created by the postgres image bootstrap.
    allowed = {'ERROR:  role "postgres" already exists', 'ERROR:  database "platform" already exists'}
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if any(line not in allowed for line in lines) or len(lines) != len(set(lines)):
        raise RuntimeError('Unexpected SQL restore diagnostics; inspect private SQL logs')


def store_volume_restore_targets(bundle):
    path = bundle / 'store-recovery.json'
    if not path.exists():
        return []
    manifest = json.loads(path.read_text())
    providers = {row['provider'] for row in manifest['resources'] if row['state'] != 'purged'} - {'postgresql'}
    mapping = {'s3': ('rustfs', 'rustfs_data', 'rustfs-data.tar.gz'),
        'qdrant': ('qdrant', 'qdrant_data', 'qdrant-storage.tar.gz'),
        'opensearch': ('opensearch', 'opensearch_data', 'opensearch-data.tar.gz')}
    if providers - mapping.keys():
        raise RuntimeError('No protected restore adapter for a retained data-store provider')
    result = [mapping[provider] for provider in sorted(providers)]
    if any(not (bundle / filename).is_file() for _, _, filename in result):
        raise RuntimeError('A retained data-store volume is missing from this recovery bundle')
    return result


def quarantine_hosted_access(compose):
    """A restored authorization catalog must not activate routes before explicit reconciliation."""
    statement = b"""DO $$ BEGIN
        IF to_regclass('public.store_resources') IS NOT NULL THEN
            CREATE TABLE IF NOT EXISTS store_control (singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton), recovery_required BOOLEAN NOT NULL DEFAULT false);
            INSERT INTO store_control(singleton,recovery_required) VALUES(true,true)
                ON CONFLICT(singleton) DO UPDATE SET recovery_required=true;
            UPDATE store_credentials SET expires_at=LEAST(expires_at,now()) WHERE state<>'revoked';
        END IF;
        IF to_regclass('public.hosted_access_metadata') IS NOT NULL THEN
            INSERT INTO hosted_access_metadata(key,value) VALUES ('recovery-required','true')
                ON CONFLICT(key) DO UPDATE SET value='true';
            UPDATE hosted_access_metadata SET value=(value::text::bigint+1)::text::jsonb WHERE key='generation';
        END IF;
    END $$;"""
    run(compose + ['exec', '-T', 'postgres', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                   '-U', 'postgres', '-d', 'platform'], ROOT, data=statement)


def latest_store_intents(instance='node-01'):
    """Read purge intents from the latest verified point, even for an older data restore."""
    restic = '/usr/local/sbin/platform-restic'
    snapshots = json.loads(run([restic, 'snapshots', '--json', '--host', instance,
        '--tag', 'developer-platform,verified']))
    if not snapshots:
        raise RuntimeError('No verified recovery intent snapshot')
    from datetime import datetime
    latest = max(snapshots, key=lambda row: datetime.fromisoformat(row['time'].replace('Z','+00:00')))
    if not re.fullmatch('[0-9a-f]{64}', latest['id']) or len(latest.get('paths', [])) != 1:
        raise RuntimeError('Ambiguous recovery intent snapshot')
    prefix = latest['paths'][0].rstrip('/')
    manifest = json.loads(run([restic, 'dump', latest['id'], prefix + '/manifest.json']))
    data = run([restic, 'dump', latest['id'], prefix + '/store-recovery.json'])
    if hashlib.sha256(data).hexdigest() != manifest.get('sha256', {}).get('store-recovery.json'):
        raise RuntimeError('Latest verified store intent checksum mismatch')
    return data


def recover(bundle, projects):
    verify(bundle)
    if ROOT.exists():
        raise RuntimeError('Platform directory exists; use a fresh recovery VM')
    if run(['docker', 'ps', '-aq']).strip() or run(['docker', 'volume', 'ls', '-q']).strip():
        raise RuntimeError('Recovery Docker daemon must contain no containers or volumes')
    ROOT.mkdir(mode=0o700, parents=True)
    extract(bundle / 'platform-files.tar.gz', ROOT)
    ROOT.chmod(0o700)
    env = ROOT / '.env'
    values = dict(line.split('=', 1) for line in env.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith('#'))
    values.update(EDGE_BIND_IP='127.0.0.1', PLATFORM_DOMAIN='platform.localhost',
                  APPS_DOMAIN='apps.localhost', TLS_EMAIL='admin@example.com',
                  ALERTMANAGER_CONFIG_DIR='.')
    env.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
    env.chmod(0o600)
    (ROOT / 'infrastructure/proxy/Caddyfile').write_text('''http://platform.localhost {
 reverse_proxy platform-api:8000
}
https://platform.localhost {
 tls internal
 reverse_proxy platform-api:8000
}
http://*.apps.localhost {
 reverse_proxy k3d-workloads-serverlb:80
}
https://*.apps.localhost {
 tls internal
 reverse_proxy k3d-workloads-serverlb:80
}
''')
    (ROOT / 'infrastructure/monitoring/alertmanager.yaml').write_text(
        'route:\n  receiver: recovery-no-notifications\nreceivers:\n  - name: recovery-no-notifications\n')
    (ROOT / 'compose.override.yaml').write_text('''services:
  grafana:
    environment:
      GF_UNIFIED_ALERTING_ENABLED: "false"
      GF_SMTP_ENABLED: "false"
''')
    compose = ['docker', 'compose']
    run(compose + ['config', '--quiet'], ROOT)
    run(compose + ['up', '-d', '--wait', '--wait-timeout', '120', 'postgres'], ROOT, timeout=900)
    logs = ROOT / '.runtime/recovery'
    logs.mkdir(mode=0o700, parents=True)
    (ROOT / '.runtime/bin').mkdir(mode=0o700, exist_ok=True)
    import shutil
    shutil.copy2('/usr/local/bin/kubectl', ROOT / '.runtime/bin/kubectl')
    # Stream a private SQL dump to psql; retain every diagnostic and check the whitelist.
    with gzip.open(bundle / 'postgres.sql.gz', 'rb') as source, \
         (logs / 'restore.stdout').open('wb') as out, (logs / 'restore.stderr').open('wb') as err:
        proc = subprocess.Popen(compose + ['exec', '-T', 'postgres', 'psql', '-X', '-U', 'postgres', '-d', 'postgres'],
                                cwd=ROOT, stdin=subprocess.PIPE, stdout=out, stderr=err)
        try:
            while chunk := source.read(1024 * 1024):
                proc.stdin.write(chunk)
            proc.stdin.close()
            if proc.wait(timeout=600):
                raise RuntimeError('SQL import process failed')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    check_import_errors((logs / 'restore.stderr').read_text())
    quarantine_hosted_access(compose)
    has_named_stores = run(compose + ['exec','-T','postgres','psql','-X','-A','-t','-U','postgres',
        '-d','platform','-c',"SELECT to_regclass('public.store_resources') IS NOT NULL"], ROOT).strip() == b't'
    store_intents = None
    if has_named_stores:
        if not (ROOT / 'platform/app/src/app/stores/recovery.py').is_file():
            raise RuntimeError('Named-store restore requires quarantine-capable source before services may start')
        store_intents = latest_store_intents()

    store_volumes = store_volume_restore_targets(bundle)
    run(compose + ['create', 'proxy', 'grafana', *[service for service, _, _ in store_volumes]], ROOT, timeout=900)
    for volume, filename in [('caddy_data', 'proxy-data.tar.gz'), ('caddy_config', 'proxy-config.tar.gz'),
                              ('grafana', 'grafana-grafana.tar.gz'), *[(volume, filename) for _, volume, filename in store_volumes]]:
        destination = Path(run(['docker', 'volume', 'inspect', '--format', '{{ .Mountpoint }}',
                               'developer-platform_' + volume]).decode().strip())
        if any(not p.is_dir() or p.is_symlink() for p in destination.rglob('*')):
            raise RuntimeError('Service volume contains unexpected data')
        # data filter permits safe paths; preserve numeric ownership for Grafana's UID.
        with tarfile.open(bundle / filename) as archive:
            def owned(member, path):
                safe = tarfile.data_filter(member, path)
                if safe is not None:
                    safe.uid, safe.gid = member.uid, member.gid
                return safe
            archive.extractall(destination, filter=owned, numeric_owner=True)
    run(['python3', 'scripts/install-k3d.py'], ROOT, timeout=300)
    run(['bash', 'scripts/up.sh'], ROOT, timeout=1200)
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5) as response:
                if json.load(response)['status'] == 'ready':
                    break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise RuntimeError('API readiness timed out')
    access_token = os.environ.get('PLATFORM_ACCESS_TOKEN')
    if not access_token:
        raise RuntimeError('PLATFORM_ACCESS_TOKEN is required for authorized project recovery')
    headers = {'Authorization': 'Bearer ' + access_token, 'Content-Type': 'application/json'}
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/projects', headers=headers), timeout=15) as response:
        catalog = json.load(response)
    if store_intents is not None:
        checksum = hashlib.sha256(store_intents).hexdigest()
        run(compose + ['exec','-T','platform-api','python','-m','app.stores.recovery',
            '--apply','--manifest-sha256',checksum], ROOT, data=store_intents, timeout=900)
        print('Named stores reconciled; all recovered grants remain revoked. Fresh owner approval/bindings are required.')
    for name in projects:
        selected = [p for p in catalog if p['name'] == name and p['spec']['name'] == name]
        if len(selected) != 1:
            raise RuntimeError('Selected project absent from restored catalog')
        if any(c.get('bindings') for c in selected[0]['spec'].get('components', [])):
            raise RuntimeError('Recovered store consumers require fresh explicit approval and updated bindings before reapply')
        request = urllib.request.Request('http://127.0.0.1:8000/projects/' + name,
                                         headers=headers, data=json.dumps(selected[0]['spec']).encode(), method='PUT')
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 202:
                raise RuntimeError('Project reapply was not accepted')
            accepted = json.load(response)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            status_request = urllib.request.Request(
                'http://127.0.0.1:8000' + accepted['status_url'], headers=headers)
            with urllib.request.urlopen(status_request, timeout=15) as response:
                operation = json.load(response)
            if operation['state'] == 'succeeded':
                break
            if operation['state'] == 'failed':
                raise RuntimeError('Project reapply failed; operation ' + accepted['operation_id'])
            time.sleep(2)
        else:
            raise TimeoutError('Project reapply timed out; operation ' + accepted['operation_id'])
        print('Project secrets restored for ' + name if restore_project_secrets(bundle, name)
              else 'No project secrets in the bundle for ' + name)
    print('Restoration completed; run acceptance checks next.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--project', action='append', required=True)
    args = parser.parse_args()
    if any(not re.fullmatch('[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?', n) for n in args.project):
        parser.error('Invalid project name')
    os.umask(0o077)
    recover(args.bundle, args.project)
