"""Disposable real Keycloak → pgAdmin SSO and lease-bound connection checks.

Loopback HTTP and host networking are fixture-only; production uses HTTPS and
isolated Compose networks. No existing platform/identity installation is used.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from uuid import uuid4
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'dpage/pgadmin4:9.18@sha256:c332c5f6dfba995d9ebc4af261d93506d6876085d712eaaa3defc8dd1a3f26de'


def port():
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Disposable console container operation failed')
    return result


def ready(url, container, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(.5)
    state = subprocess.run(['docker', 'inspect', '--format',
        '{{.State.Running}} {{.State.OOMKilled}} {{.State.ExitCode}}', container],
        capture_output=True, text=True, timeout=10)
    if state.returncode:
        raise RuntimeError('Console fixture readiness failed; container state unavailable')
    running, oom_killed, exit_code = state.stdout.strip().split()
    if running != 'true':
        reason = 'OOM-killed' if oom_killed == 'true' else 'exited with code ' + exit_code
        raise RuntimeError('Console fixture container ' + reason)
    raise RuntimeError('Console fixture readiness failed while container was running')


def run(connection, expire_url):
    """connection is kept in memory/stdin and never printed or stored in reports."""
    for candidate in ('quay.io/keycloak/keycloak:26.4.1', IMAGE):
        inspected = subprocess.run(['docker', 'image', 'inspect', candidate], capture_output=True, timeout=15)
        if inspected.returncode:
            subprocess.run(['docker', 'pull', candidate], capture_output=True, check=True, timeout=300)
    identity_port, console_port = port(), port()
    issuer = f'http://127.0.0.1:{identity_port}/realms/platform'
    base = f'http://127.0.0.1:{console_port}/store-console/postgresql'
    secret, password, other_password = secrets.token_urlsafe(32), secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    containers = []
    with tempfile.TemporaryDirectory(prefix='store-console-') as directory:
        directory = Path(directory)
        realm = {'realm': 'platform', 'enabled': True, 'registrationAllowed': False,
            'users': [{'username': 'fixture', 'enabled': True, 'firstName': 'Store', 'lastName': 'Fixture',
                'email': 'fixture@example.com', 'emailVerified': True,
                'credentials': [{'type': 'password', 'value': password, 'temporary': False}]},
                {'username': 'other', 'enabled': True, 'firstName': 'Other', 'lastName': 'Fixture',
                 'email': 'other@example.com', 'emailVerified': True,
                 'credentials': [{'type': 'password', 'value': other_password, 'temporary': False}]}],
            'clients': [{'clientId': 'platform-store-console', 'enabled': True, 'protocol': 'openid-connect',
                'publicClient': False, 'secret': secret, 'standardFlowEnabled': True,
                'directAccessGrantsEnabled': False, 'serviceAccountsEnabled': False,
                'redirectUris': [base + '/oauth2/authorize'],
                'attributes': {'pkce.code.challenge.method': 'S256'}}]}
        realm_path = directory / 'realm.json'
        realm_path.write_text(json.dumps(realm)); realm_path.chmod(0o644)
        config_path = directory / 'config_local.py'
        config_path.write_text((ROOT / 'infrastructure/persistence/console/config_local.py').read_text() +
            f"\n# Loopback-only disposable fixture overrides; never used by Compose.\nOAUTH2_CONFIG[0]['OAUTH2_SERVER_METADATA_URL'] = {issuer + '/.well-known/openid-configuration'!r}\nSESSION_COOKIE_SECURE = False\n")
        config_path.chmod(0o644)
        directory.chmod(0o755)  # Container identities must traverse; random fixture-only values.
        try:
            name = 'store-console-identity-' + uuid4().hex[:10]; containers.append(name)
            docker('run', '-d', '--name', name, '--network', 'host', '--memory', '1g', '--cpus', '2',
                '-v', f'{realm_path}:/opt/keycloak/data/import/platform.json:ro',
                'quay.io/keycloak/keycloak:26.4.1', 'start-dev', '--import-realm',
                '--http-host=127.0.0.1', f'--http-port={identity_port}', f'--hostname=http://127.0.0.1:{identity_port}')
            ready(issuer + '/.well-known/openid-configuration', name)
            name = 'store-console-browser-' + uuid4().hex[:10]; containers.append(name)
            docker('run', '-d', '--name', name, '--network', 'host', '--memory', '512m', '--cpus', '1',
                '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--tmpfs', '/var/lib/pgadmin:rw,uid=5050,gid=5050,size=64m',
                '-e', 'PGADMIN_DEFAULT_EMAIL=fixture-bootstrap@example.com',
                '-e', 'PGADMIN_DEFAULT_PASSWORD=' + secrets.token_urlsafe(32), '-e', 'PGADMIN_DISABLE_POSTFIX=true',
                '-e', 'PGADMIN_LISTEN_ADDRESS=127.0.0.1', '-e', f'PGADMIN_LISTEN_PORT={console_port}',
                '-e', 'STORE_CONSOLE_OIDC_SECRET=' + secret, '-e', 'IDENTITY_DOMAIN=fixture.invalid',
                '-e', 'SCRIPT_NAME=/store-console/postgresql',
                '-v', f'{config_path}:/pgadmin4/config_local.py:ro', IMAGE)
            ready(base + '/misc/ping', name)
            result = subprocess.run(['node', str(ROOT / 'platform/ui/scripts/verify-store-console.mjs')],
                input=json.dumps({'base': base, 'username': 'fixture', 'password': password,
                    'connection': connection, 'expireUrl': expire_url, 'otherUsername': 'other', 'otherPassword': other_password}), text=True, capture_output=True, timeout=90)
            if result.returncode:
                # Node prints fixed stage codes only; never forward browser/server errors.
                raise RuntimeError('Console fixture failed at ' + result.stdout.strip()[:80])
            print(result.stdout.strip())
        finally:
            for name in reversed(containers):
                subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)
