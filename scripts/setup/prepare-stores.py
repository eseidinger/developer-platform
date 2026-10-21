#!/usr/bin/env python3
"""Prepare selected store configuration without replacing existing keys or data."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile

from scripts.internal.env import settings

IMAGE = 'opensearchproject/opensearch:3.9.0@sha256:adfa61f85025d06b4aeb562e7e74fde7e31c437039c93c3862c17e9acebd6c7c'


def command(arguments, **kwargs):
    result = subprocess.run(arguments, capture_output=True, timeout=120, **kwargs)
    if result.returncode:
        raise RuntimeError('Store configuration preparation failed; inspect selected tools/image availability')
    return result.stdout


def write(path, value, mode=0o600):
    path.write_text(value)
    path.chmod(mode)


def password_hash(value):
    output = command(['docker', 'run', '--rm', '--network', 'none', '--hostname', 'localhost',
        '--memory', '256m', '--cpus', '1', '-e', 'PLATFORM_HASH_PASSWORD', '--entrypoint',
        '/usr/share/opensearch/plugins/opensearch-security/tools/hash.sh', IMAGE, '-env', 'PLATFORM_HASH_PASSWORD'],
        env={**os.environ, 'PLATFORM_HASH_PASSWORD': value}).decode()
    hashes = re.findall(r'^\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}$', output, re.MULTILINE)
    if len(hashes) != 1:
        raise RuntimeError('Native password hasher returned an invalid result')
    return hashes[0]


def service_permissions(path):
    # Bind individual keys/configuration only; the CA signing key stays private.
    # Reapply after recovery because portable source archives omit POSIX ACLs.
    files = [path / 'node-key.pem', path / 'admin-key.pem', *(path / 'bootstrap').iterdir()]
    if os.getuid() == 0:
        os.chown(path / 'bootstrap', 1000, 1000)
        for filename in files:
            os.chown(filename, 1000, 1000)
    elif os.getuid() != 1000:
        command(['setfacl', '-m', 'u:1000:rx', str(path / 'bootstrap')])
        for filename in files:
            command(['setfacl', '-m', 'u:1000:r', str(filename)])


def issue_search_certificates(stage, address, key_dir=None):
    keys = key_dir or stage
    ca_key = ['-key', str(keys / 'ca-key.pem')] if key_dir else [
        '-newkey', 'rsa:3072', '-nodes', '-keyout', str(stage / 'ca-key.pem')]
    command(['openssl', 'req', '-x509', *ca_key, '-days', '3650',
        '-subj', '/CN=Platform store authority', '-out', str(stage / 'ca.pem'),
        '-addext', 'basicConstraints=critical,CA:TRUE',
        '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
        '-addext', 'subjectKeyIdentifier=hash', '-addext', 'authorityKeyIdentifier=keyid:always'])
    for name, subject, purpose in [('node', '/CN=opensearch', 'serverAuth,clientAuth'),
                                   ('admin', '/CN=platform-store-admin', 'clientAuth')]:
        key = ['-key', str(keys / (name + '-key.pem'))] if key_dir else [
            '-newkey', 'rsa:3072', '-nodes', '-keyout', str(stage / (name + '-key.pem'))]
        command(['openssl', 'req', '-new', *key, '-subj', subject, '-out', str(stage / (name + '.csr'))])
        extension = ('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
                     'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\nextendedKeyUsage=' + purpose + '\n')
        if name == 'node':
            extension += f'subjectAltName=DNS:opensearch,DNS:localhost,IP:{address},IP:127.0.0.1\n'
        write(stage / (name + '.ext'), extension)
        command(['openssl', 'x509', '-req', '-days', '365', '-in', str(stage / (name + '.csr')),
            '-CA', str(stage / 'ca.pem'), '-CAkey', str(keys / 'ca-key.pem'), '-CAcreateserial',
            '-extfile', str(stage / (name + '.ext')), '-out', str(stage / (name + '.pem'))])
    command(['openssl', 'verify', '-x509_strict', '-purpose', 'sslserver', '-verify_ip', address,
             '-CAfile', str(stage / 'ca.pem'), str(stage / 'node.pem')])
    command(['openssl', 'verify', '-x509_strict', '-purpose', 'sslclient',
             '-CAfile', str(stage / 'ca.pem'), str(stage / 'admin.pem')])
    for path in stage.glob('*.pem'):
        path.chmod(0o600 if path.name.endswith('-key.pem') else 0o644)


def renew_search_certificates(destination, address):
    # Preserve all three private keys, native identities, data and issuer subject.
    # Build and strictly verify the complete new public chain before replacement.
    with tempfile.TemporaryDirectory(prefix='store-renew-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        issue_search_certificates(stage, address, key_dir=destination)
        for name in ('ca.pem', 'node.pem', 'admin.pem'):
            os.replace(stage / name, destination / name)


def prepare_search(root, config, renew_certificates=False):
    address = str(ipaddress.IPv4Address(config.get('OPENSEARCH_IP', '172.30.80.17')))
    destination = root / 'opensearch'
    required = ['ca.pem', 'ca-key.pem', 'node.pem', 'node-key.pem', 'admin.pem', 'admin-key.pem',
                'opensearch.yml', 'bootstrap/config.yml', 'bootstrap/internal_users.yml', 'bootstrap/roles_mapping.yml', 'identity.json']
    if destination.exists():
        if not all((destination / name).is_file() for name in required):
            raise RuntimeError('Existing OpenSearch configuration is incomplete; inspect it before retrying')
        identity = json.loads((destination / 'identity.json').read_text())
        if identity.get('address') != address:
            raise RuntimeError('OpenSearch address changed; plan certificate renewal before deployment')
        if identity.get('console_tenant_policy') != 'resource-v1':
            raise RuntimeError('OpenSearch console policy changed; use a clean setup or an explicitly reviewed native tenant migration')
        if renew_certificates:
            renew_search_certificates(destination, address)
            identity['tls_profile'] = 'strict-v1'
            write(destination / 'identity.json', json.dumps(identity))
        elif identity.get('tls_profile') != 'strict-v1':
            raise RuntimeError('Existing OpenSearch certificates require same-key renewal; run scripts/setup/prepare-stores.py --renew-opensearch-certificates, then recreate OpenSearch to load them')
        command(['openssl', 'x509', '-in', str(destination / 'node.pem'), '-checkend', '86400', '-noout'])
        service_permissions(destination)
        shutil.copy2(destination / 'ca.pem', root / 'public/opensearch-ca.pem')
        (root / 'public/opensearch-ca.pem').chmod(0o644)
        return
    for key in ('OPENSEARCH_ADMIN_PASSWORD', 'OPENSEARCH_DASHBOARDS_PASSWORD', 'STORE_OPENSEARCH_CONSOLE_COOKIE_KEY'):
        if len(config.get(key, '')) < 32:
            raise RuntimeError('Generate the required store credentials with scripts/init.py first')
    with tempfile.TemporaryDirectory(prefix='store-tls-', dir=root) as temporary:
        stage = Path(temporary)
        issue_search_certificates(stage, address)
        bootstrap = stage / 'bootstrap'; bootstrap.mkdir(mode=0o700)
        # Public image templates supply the native built-in roles/action groups.
        # Replace all demo users and mappings before the first initialization.
        for name in ('config.yml', 'roles.yml', 'roles_mapping.yml', 'internal_users.yml',
                     'action_groups.yml', 'tenants.yml', 'nodes_dn.yml', 'allowlist.yml', 'audit.yml'):
            data = command(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'cat', IMAGE,
                '/usr/share/opensearch/config/opensearch-security/' + name])
            write(bootstrap / name, data.decode())
        users = {'_meta': {'type': 'internalusers', 'config_version': 2},
            'admin': {'hash': password_hash(config['OPENSEARCH_ADMIN_PASSWORD']), 'reserved': True, 'backend_roles': ['admin']},
            'kibanaserver': {'hash': password_hash(config['OPENSEARCH_DASHBOARDS_PASSWORD']), 'reserved': True}}
        write(bootstrap / 'internal_users.yml', json.dumps(users, indent=2))
        write(bootstrap / 'roles_mapping.yml', json.dumps({'_meta': {'type': 'rolesmapping', 'config_version': 2},
            'all_access': {'backend_roles': ['admin']}, 'kibana_server': {'users': ['kibanaserver']}}, indent=2))
        basic = {'_meta': {'type': 'config', 'config_version': 2}, 'config': {'dynamic': {
            'http': {'anonymous_auth_enabled': False},
            'kibana': {'multitenancy_enabled': True, 'private_tenant_enabled': False,
                'server_username': 'kibanaserver', 'index': '.kibana'},
            'authc': {'basic_internal_auth_domain': {'http_enabled': True, 'transport_enabled': True, 'order': 0,
                'http_authenticator': {'type': 'basic', 'challenge': True}, 'authentication_backend': {'type': 'intern'}}}}}}
        write(bootstrap / 'config.yml', json.dumps(basic, indent=2))
        service_permissions(stage)
        server = {'cluster.name': 'platform-stores', 'network.host': '0.0.0.0', 'discovery.type': 'single-node',
            'node.store.allow_mmap': False, 'action.destructive_requires_name': True,
            'plugins.security.ssl.transport.pemcert_filepath': 'node.pem',
            'plugins.security.ssl.transport.pemkey_filepath': 'node-key.pem',
            'plugins.security.ssl.transport.pemtrustedcas_filepath': 'ca.pem',
            'plugins.security.ssl.transport.enforce_hostname_verification': True,
            'plugins.security.ssl.http.enabled': True, 'plugins.security.ssl.http.pemcert_filepath': 'node.pem',
            'plugins.security.ssl.http.clientauth_mode': 'OPTIONAL',
            'plugins.security.ssl.http.pemkey_filepath': 'node-key.pem',
            'plugins.security.ssl.http.pemtrustedcas_filepath': 'ca.pem',
            'plugins.security.authcz.admin_dn': ['CN=platform-store-admin'],
            'plugins.security.nodes_dn': ['CN=opensearch'],
            'plugins.security.allow_default_init_securityindex': False,
            'plugins.security.restapi.roles_enabled': ['all_access', 'security_rest_api_access']}
        write(stage / 'opensearch.yml', json.dumps(server, indent=2), 0o644)
        write(stage / 'identity.json', json.dumps({'address': address, 'image': IMAGE, 'console_tenant_policy': 'resource-v1', 'tls_profile': 'strict-v1'}))
        # Keep only protected configuration, not temporary CSRs and extensions.
        for pattern in ('*.csr', '*.ext', '*.srl'):
            for path in stage.glob(pattern):
                path.unlink()
        os.rename(stage, destination)
    shutil.copy2(destination / 'ca.pem', root / 'public/opensearch-ca.pem')
    (root / 'public/opensearch-ca.pem').chmod(0o644)


def prepare(root, config, renew_certificates=False):
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    (root / 'public').mkdir(mode=0o755, exist_ok=True)
    if 'opensearch' in config.get('COMPOSE_PROFILES', '').split(','):
        prepare_search(root, config, renew_certificates=renew_certificates)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--renew-opensearch-certificates', action='store_true', help='Reissue the public chain with existing private keys; recreate OpenSearch afterwards')
        args = parser.parse_args()
        config = settings()
        for key in ('COMPOSE_PROFILES', 'OPENSEARCH_IP', 'OPENSEARCH_ADMIN_PASSWORD', 'OPENSEARCH_DASHBOARDS_PASSWORD', 'STORE_OPENSEARCH_CONSOLE_COOKIE_KEY'):
            if key in os.environ:
                config[key] = os.environ[key]
        prepare(Path('.runtime/stores'), config, renew_certificates=args.renew_opensearch_certificates)
        print('Selected store configuration prepared; existing keys and volumes retained.')
    except Exception as error:
        print('Store preparation failed: ' + str(error), file=__import__('sys').stderr)
        raise SystemExit(1)
