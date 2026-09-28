#!/usr/bin/env python3
"""Exercise k3d or Docker availability and recover the existing lab."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request


def command(*args, timeout=60, check=True, cwd=None):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, timeout=timeout, check=False, cwd=cwd)
    if check and result.returncode:
        raise RuntimeError('command failed: ' + args[0])
    return result


def save(path, evidence):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(evidence, indent=2) + '\n')
    os.replace(temporary, path)


def wait_for(description, predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(5)
    raise RuntimeError('timed out waiting for ' + description)


def prometheus_value(query):
    url = 'http://127.0.0.1:9090/api/v1/query?' + urllib.parse.urlencode({'query': query})
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.load(response)
        result = payload.get('data', {}).get('result', [])
        return result[0]['value'][1] if result else None
    except Exception:
        return None


def url_ready(url):
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return response.status == 200
    except Exception:
        return False


def postgres_healthy():
    result = command('docker', 'inspect', '--format', '{{.State.Health.Status}}',
                     'developer-platform-postgres-1', check=False)
    return result.returncode == 0 and result.stdout.strip() == 'healthy'


def refresh_k3d_load_balancer():
    command('docker', 'restart', 'k3d-workloads-serverlb', timeout=120)


def reconcile_platform(platform_dir, timeout):
    # Docker can reassign a fixed service address to a dynamically addressed
    # container while restarting everything concurrently. Remove only Compose
    # containers so up.sh can claim PostgreSQL's fixed address first. Named
    # volumes and the k3d/shared network remain intact.
    command('docker', 'compose', 'stop', '--timeout', '60', timeout=180,
            cwd=platform_dir)
    command('docker', 'compose', 'rm', '--force', timeout=180,
            cwd=platform_dir)
    command('bash', 'scripts/up.sh', timeout=timeout, cwd=platform_dir)


def nodes_ready(kubeconfig):
    result = command('kubectl', '--kubeconfig', kubeconfig, 'get', 'nodes', '-o', 'json', check=False)
    if result.returncode:
        return False
    try:
        nodes = json.loads(result.stdout)['items']
        return len(nodes) == 3 and all(any(c['type'] == 'Ready' and c['status'] == 'True'
                                           for c in n['status'].get('conditions', [])) for n in nodes)
    except (KeyError, TypeError, json.JSONDecodeError):
        return False


def run(args):
    report = Path(args.report)
    report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence = {'mode': args.mode, 'started_at': int(time.time()),
                'email_receipt': 'operator confirmation required', 'result': 'running'}
    save(report, evidence)
    recovered = False
    try:
        if command('systemctl', 'is-active', '--quiet', 'docker', check=False).returncode:
            raise RuntimeError('Docker must be active before the drill')
        kubeconfig = str(Path(args.platform_dir) / '.runtime/admin.kubeconfig')
        if not postgres_healthy() or not url_ready('http://127.0.0.1:8000/readyz'):
            raise RuntimeError('PostgreSQL and the platform API must be ready before the drill')
        if args.mode == 'cluster':
            if command('docker', 'inspect', '--format', '{{.State.Running}}', args.cluster_container).stdout.strip() != 'true':
                raise RuntimeError('k3d server container must be running before the drill')
            if not nodes_ready(kubeconfig):
                raise RuntimeError('all three Kubernetes nodes must be Ready before the drill')
            evidence['baseline_nodes_ready'] = True
            evidence['action'] = 'stop cluster server container'
            save(report, evidence)
            command('docker', 'stop', '--time', '30', args.cluster_container, timeout=90)
            wait_for('kubernetes-state target down',
                     lambda: prometheus_value('up{job="kubernetes-state"}') == '0', args.down_timeout)
            evidence['target_down_at'] = int(time.time())
            wait_for('ScrapeTargetDown firing', lambda: prometheus_value(
                'ALERTS{alertname="ScrapeTargetDown",alertstate="firing",job="kubernetes-state"}') == '1',
                args.alert_timeout)
            evidence['alert_firing_at'] = int(time.time())
            save(report, evidence)
            time.sleep(args.notification_wait)
            command('docker', 'start', args.cluster_container, timeout=90)
            refresh_k3d_load_balancer()
            wait_for('all Kubernetes nodes Ready', lambda: nodes_ready(kubeconfig), args.recovery_timeout)
            wait_for('kubernetes-state target up',
                     lambda: prometheus_value('up{job="kubernetes-state"}') == '1', args.recovery_timeout)
            wait_for('ScrapeTargetDown resolved', lambda: prometheus_value(
                'ALERTS{alertname="ScrapeTargetDown",alertstate="firing",job="kubernetes-state"}') is None,
                args.recovery_timeout)
        else:
            evidence['action'] = 'stop Docker service'
            evidence['outage_wait_seconds'] = args.docker_outage_wait
            save(report, evidence)
            command('systemctl', 'stop', 'docker', timeout=120)
            time.sleep(args.docker_outage_wait)
            command('systemctl', 'start', 'docker', timeout=120)
            wait_for('Docker active', lambda: command('systemctl', 'is-active', '--quiet', 'docker', check=False).returncode == 0,
                     args.recovery_timeout)
            reconcile_platform(args.platform_dir, args.recovery_timeout)
            wait_for('PostgreSQL healthy', postgres_healthy, args.recovery_timeout)
            wait_for('platform API ready', lambda: url_ready('http://127.0.0.1:8000/readyz'),
                     args.recovery_timeout)
            wait_for('Prometheus ready', lambda: command('wget', '-q', '-O', '/dev/null', 'http://127.0.0.1:9090/-/ready', check=False).returncode == 0,
                     args.recovery_timeout)
            wait_for('all Kubernetes nodes Ready', lambda: nodes_ready(kubeconfig), args.recovery_timeout)
            wait_for('heartbeat timer active', lambda: command('systemctl', 'is-active', '--quiet', 'platform-heartbeat.timer', check=False).returncode == 0,
                     args.recovery_timeout)
        recovered = True
        evidence.update(result='passed', finished_at=int(time.time()), recovered=True)
        save(report, evidence)
    finally:
        if not recovered:
            if args.mode == 'cluster':
                command('docker', 'start', args.cluster_container, timeout=90, check=False)
            else:
                command('systemctl', 'start', 'docker', timeout=120, check=False)
            evidence.update(result='failed', finished_at=int(time.time()), recovered=False)
            save(report, evidence)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['cluster', 'docker'], required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--platform-dir', default='/opt/developer-platform')
    parser.add_argument('--cluster-container', default='k3d-workloads-server-0')
    parser.add_argument('--down-timeout', type=int, default=180)
    parser.add_argument('--alert-timeout', type=int, default=300)
    parser.add_argument('--notification-wait', type=int, default=90)
    parser.add_argument('--docker-outage-wait', type=int, default=360)
    parser.add_argument('--recovery-timeout', type=int, default=600)
    options = parser.parse_args()
    if min(options.down_timeout, options.alert_timeout, options.notification_wait,
           options.docker_outage_wait, options.recovery_timeout) < 30:
        parser.error('all timeouts must be at least 30 seconds')
    try:
        run(options)
    except Exception as error:
        print('Availability drill failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
