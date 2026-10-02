#!/usr/bin/env python3
"""Check a restored platform, or explicitly seed a pre-backup database marker."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import uuid


def command(args, root, data=None, timeout=30):
    result = subprocess.run(args, cwd=root, input=data, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed: ' + args[0] + ' (output suppressed to protect credentials)')
    return result.stdout


def settings(root):
    return dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#'))


def request(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=10) as response:
        return response.read()


def retry(action, seconds=90):
    deadline = time.monotonic() + seconds
    while True:
        try:
            return action()
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


def check_grafana():
    if json.loads(request('http://127.0.0.1:3000/api/health')).get('database') != 'ok':
        raise RuntimeError('Grafana database unhealthy')


def check_targets():
    data = json.loads(request('http://127.0.0.1:9090/api/v1/targets'))
    targets = data['data']['activeTargets']
    if not targets or any(t['health'] != 'up' for t in targets):
        raise RuntimeError('Prometheus targets unhealthy')


def verify_bundle(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('format') != 1 or not manifest.get('sha256'):
        raise RuntimeError('Invalid manifest')
    for name, expected in manifest['sha256'].items():
        p = bundle / name
        if Path(name).name != name or p.is_symlink() or not p.is_file():
            raise RuntimeError('Unsafe or missing manifest file')
        with p.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise RuntimeError('Bundle checksum mismatch')
    return manifest


def marker_sql(marker):
    if not re.fullmatch('[a-f0-9]{32}', marker.get('value', '')) or not re.fullmatch('recovery_marker_[a-f0-9]{32}', marker.get('table', '')):
        raise RuntimeError('Invalid marker receipt')
    return "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM public.\"%s\" WHERE value='%s') THEN RAISE EXCEPTION 'marker missing'; END IF; END $$;" % (marker['table'], marker['value'])


def test_pod(project, image, marker=None):
    database = 'project_' + project.replace('-', '_')
    sql = """BEGIN;
CREATE TEMP TABLE recovery_probe(value text);
INSERT INTO recovery_probe VALUES ('recovery-ok');
DO $$ BEGIN
IF current_user <> '%s' OR current_database() <> '%s' THEN RAISE EXCEPTION 'wrong identity'; END IF;
IF (SELECT value FROM recovery_probe) <> 'recovery-ok' THEN RAISE EXCEPTION 'readback mismatch'; END IF;
IF has_database_privilege(current_user, 'platform', 'CONNECT') THEN RAISE EXCEPTION 'catalog access allowed'; END IF;
END $$;
%s
ROLLBACK;
""" % (database, database, marker_sql(marker) if marker else '')
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
        'name': 'recovery-check-' + uuid.uuid4().hex[:12], 'namespace': 'project-' + project},
        'spec': {'restartPolicy': 'Never', 'activeDeadlineSeconds': 180,
                 'automountServiceAccountToken': False,
                 'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001,
                                     'seccompProfile': {'type': 'RuntimeDefault'}},
                 'containers': [{'name': 'check', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                     'envFrom': [{'secretRef': {'name': 'database'}}],
                     'env': [{'name': 'PGCONNECT_TIMEOUT', 'value': '10'}],
                     'command': ['/bin/sh', '-ec'],
                     # Kubelet expands $$ to $ before the shell sees its quoted heredoc.
                     'args': ["sleep 15\npsql -X -v ON_ERROR_STOP=1 <<'SQL'\n" + sql.replace('$', '$$') + "SQL\n"],
                     'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                         'capabilities': {'drop': ['ALL']}},
                     'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                                   'limits': {'cpu': '500m', 'memory': '256Mi'}}}]}}


def check_pod(root, project, image, marker):
    pod = test_pod(project, image, marker)
    k = [str(root / '.runtime/bin/kubectl'), '--kubeconfig', str(root / '.runtime/admin.kubeconfig'),
         '--request-timeout=10s', '-n', 'project-' + project]
    name = pod['metadata']['name']
    command(k + ['create', '-f', '-'], root, json.dumps(pod))
    try:
        deadline = time.monotonic() + 210
        while time.monotonic() < deadline:
            status = json.loads(command(k + ['get', 'pod', name, '-o', 'json'], root))['status']
            if status['phase'] == 'Succeeded':
                return
            if status['phase'] == 'Failed':
                raise RuntimeError('Database pod failed: check credentials, permissions, or marker')
            reasons = [c.get('state', {}).get('waiting', {}).get('reason') for c in status.get('containerStatuses', [])]
            if any(r in ['ErrImagePull', 'ImagePullBackOff', 'ErrImageNeverPull', 'CreateContainerConfigError'] for r in reasons):
                raise RuntimeError('Database pod cannot start: ' + ', '.join(r for r in reasons if r))
            time.sleep(2)
        raise RuntimeError('Database pod timed out')
    except Exception as error:
        error.recovery_pod = name
        error.recovery_namespace = 'project-' + project
        raise
    finally:
        # Preserve failed pods for inspection; successful checks leave no pod behind.
        if 'status' in locals() and status.get('phase') == 'Succeeded':
            command(k + ['delete', 'pod', name, '--wait=false', '--ignore-not-found'], root)


def seed(root, project, receipt):
    marker = {'project': project, 'table': 'recovery_marker_' + uuid.uuid4().hex,
              'value': uuid.uuid4().hex, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    # Reserve receipt before mutating the source. If execution fails it is not valid evidence.
    with receipt.open('x') as output:
        json.dump({**marker, 'seeded': False}, output, indent=2)
    code = '''import os,hashlib,hmac,json,psycopg
from psycopg import sql
m=json.loads(%r)
p=hmac.new(os.environ['DATABASE_KEY'].encode(),m['project'].encode(),hashlib.sha256).hexdigest()
db='project_'+m['project'].replace('-','_')
with psycopg.connect(host=os.environ['POSTGRES_HOST'],dbname=db,user=db,password=p,connect_timeout=10) as c:
 c.execute(sql.SQL('CREATE TABLE public.{} (value text NOT NULL)').format(sql.Identifier(m['table'])))
 c.execute(sql.SQL('INSERT INTO public.{} VALUES (%%s)').format(sql.Identifier(m['table'])),(m['value'],))
''' % json.dumps(marker)
    command(['docker', 'compose', 'exec', '-T', 'platform-api', 'python', '-'], root, code)
    receipt.write_text(json.dumps({**marker, 'seeded': True}, indent=2) + '\n')
    print('Marker committed. Keep receipt independently; take a new backup now.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check', 'seed-marker'])
    p.add_argument('--platform-dir', type=Path, default=Path('/opt/developer-platform'))
    p.add_argument('--project', default='smoke')
    p.add_argument('--bundle', type=Path, default=Path('/root/platform-recovery/bundle'))
    p.add_argument('--marker', type=Path, help='Independent marker receipt; required for seed-marker')
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    if not re.fullmatch('[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?', args.project):
        p.error('Invalid project name')
    os.umask(0o077)
    root = args.platform_dir.resolve()
    if args.action == 'seed-marker':
        if not args.marker:
            p.error('--marker is required')
        seed(root, args.project, args.marker)
        return
    report_path = args.report or root / '.runtime/recovery' / ('checks-' + uuid.uuid4().hex + '.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwriting prior evidence.
    output = report_path.open('x')
    report = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'checks': [],
              'project': args.project, 'historical_data_verified': False,
              'limits': ['No full RTO measurement', 'No public DNS/TLS or live alert delivery test',
                         'No denied network destination test', 'No application-level database transaction test']}
    started = time.monotonic()
    stage = 'recovery configuration guard'
    try:
        cfg = settings(root)
        access_token = os.environ.get('PLATFORM_ACCESS_TOKEN')
        if not access_token:
            raise RuntimeError('PLATFORM_ACCESS_TOKEN is required for authorized recovery checks')
        if cfg.get('EDGE_BIND_IP') != '127.0.0.1' or cfg.get('APPS_DOMAIN') != 'apps.localhost' or cfg.get('PLATFORM_DOMAIN') != 'platform.localhost':
            raise RuntimeError('Requires recovery-only loopback and localhost domains')
        stage = 'bundle checksums'
        manifest = verify_bundle(args.bundle)
        report['backup_captured_at'] = manifest['captured_at']
        report['backup_run_id'] = manifest['run_id']
        report['checks'].append(stage)
        stage = 'API readiness and catalog'
        def ready():
            if json.loads(request('http://127.0.0.1:8000/readyz')).get('status') != 'ready':
                raise RuntimeError('API not ready')
        retry(ready)
        projects = json.loads(request('http://127.0.0.1:8000/projects', {'Authorization': 'Bearer ' + access_token}))
        if not any(v['name'] == args.project for v in projects):
            raise RuntimeError('Project missing from restored catalog')
        report['checks'].append(stage)
        stage = 'project rollout'
        command([str(root / '.runtime/bin/kubectl'), '--kubeconfig', str(root / '.runtime/admin.kubeconfig'),
                 '--request-timeout=10s', '-n', 'project-' + args.project, 'rollout', 'status',
                 'deployment/' + args.project, '--timeout=120s'], root, timeout=135)
        report['checks'].append(stage)
        stage = 'HTTP ingress'
        retry(lambda: request('http://127.0.0.1/', {'Host': args.project + '.apps.localhost'}))
        report['checks'].append(stage)
        stage = 'monitoring: Prometheus readiness'
        retry(lambda: request('http://127.0.0.1:9090/-/ready'), seconds=180)
        report['checks'].append(stage)
        stage = 'monitoring: Grafana database health'
        retry(check_grafana, seconds=180)
        report['checks'].append(stage)
        stage = 'monitoring: Prometheus scrape targets'
        retry(check_targets, seconds=180)
        report['checks'].append(stage)
        stage = 'Kubernetes database authentication, write/read and catalog privilege'
        marker = json.loads(args.marker.read_text()) if args.marker else None
        if marker and (marker.get('project') != args.project or marker.get('seeded') is not True):
            raise RuntimeError('Marker receipt does not match project or was not seeded')
        if marker:
            marker_sql(marker)
            if datetime.datetime.fromisoformat(marker['created_at']).timestamp() > manifest['captured_at']:
                raise RuntimeError('Marker was created after this backup')
        compose = json.loads(command(['docker', 'compose', 'config', '--format', 'json'], root))
        check_pod(root, args.project, compose['services']['postgres']['image'], marker)
        report['checks'].append(stage)
        report['historical_data_verified'] = marker is not None
        report['result'] = 'passed'
    except Exception as error:
        report.update(result='failed', failed_stage=stage, error_type=type(error).__name__)
        if hasattr(error, 'recovery_pod'):
            report['diagnostic_pod'] = error.recovery_pod
            report['diagnostic_namespace'] = error.recovery_namespace
            print('Diagnostic pod retained: ' + error.recovery_namespace + '/' + error.recovery_pod)
    finally:
        report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report['test_duration_seconds'] = round(time.monotonic() - started, 2)
        json.dump(report, output, indent=2)
        output.close()
    print(report['result'].upper() + ': ' + str(report_path))
    if report['result'] != 'passed':
        raise SystemExit('Failed stage: ' + stage)
    if not report['historical_data_verified']:
        print('Historical data not verified: supply an independent pre-backup marker receipt.')


if __name__ == '__main__':
    main()
