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


def check_import_errors(stderr):
    # pg_dumpall meets the two objects created by the postgres image bootstrap.
    allowed = {'ERROR:  role "postgres" already exists', 'ERROR:  database "platform" already exists'}
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if any(line not in allowed for line in lines) or len(lines) != len(set(lines)):
        raise RuntimeError('Unexpected SQL restore diagnostics; inspect private SQL logs')


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
                  APPS_DOMAIN='apps.localhost', TLS_EMAIL='admin@example.com')
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
    run(compose + ['create', 'proxy', 'grafana'], ROOT, timeout=900)
    for volume, filename in [('caddy_data', 'proxy-data.tar.gz'), ('caddy_config', 'proxy-config.tar.gz'),
                              ('grafana', 'grafana-grafana.tar.gz')]:
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
    headers = {'Authorization': 'Bearer ' + values['PLATFORM_TOKEN'], 'Content-Type': 'application/json'}
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/projects', headers=headers), timeout=15) as response:
        catalog = json.load(response)
    for name in projects:
        selected = [p for p in catalog if p['name'] == name and p['spec']['name'] == name]
        if len(selected) != 1:
            raise RuntimeError('Selected project absent from restored catalog')
        request = urllib.request.Request('http://127.0.0.1:8000/projects/' + name,
                                         headers=headers, data=json.dumps(selected[0]['spec']).encode(), method='PUT')
        with urllib.request.urlopen(request, timeout=180) as response:
            if json.load(response).get('status') != 'applied':
                raise RuntimeError('Project reapply failed')
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
