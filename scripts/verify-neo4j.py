#!/usr/bin/env python3
"""Disposable Community identity/protocol/isolation fixture; never logs native errors."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
import subprocess
import time
from uuid import uuid4
from app.stores.neo4j_controller import Controller, names
from app.stores import catalog
from app.stores.relay import Relay


def command(*args):
    result = subprocess.run(args, capture_output=True, timeout=90)
    if result.returncode: raise RuntimeError('Disposable Neo4j command failed')
    return result.stdout


def main():
    os.environ.update(NEO4J_CONTROLLER_KEY=secrets.token_hex(32), DATABASE_KEY=secrets.token_hex(32),
        NEO4J_INSTANCE_PREFIX='fixture-neo4j-' + uuid4().hex[:8] + '-', NEO4J_NETWORK_MEMBERS='')
    controller = Controller()
    resources = [uuid4(), uuid4()]
    try:
        for rid in resources:
            controller.ensure(rid)
            for _ in range(120):
                try:
                    controller.query(rid, 'RETURN 1', database='neo4j')
                    break
                except Exception: time.sleep(.5)
            else:
                import re
                logs = command('docker', 'logs', names(rid)[0]).decode(errors='replace')
                # Configuration keys/classes only; never print native log lines.
                print('Startup config keys:', sorted(set(re.findall(r'(?:dbms|server|browser)\.[a-zA-Z0-9_.]+', logs))))
                print('Startup categories:', [key for key, marker in {'disk_exhausted':'No space left', 'permissions':'Permission denied', 'tmp_budget':'Insufficient space', 'access_denied':'AccessDenied'}.items() if marker in logs])
                print('Startup exception classes:', sorted(set(re.findall(r'\b[A-Za-z]+(?:Exception|Error)\b', logs))))
                raise AssertionError('Community fixture readiness failed')
        cid, other = uuid4(), uuid4()
        password = catalog.secret_for(cid)
        for credential in (cid, other):
            controller.apply(resources[0], 'issue', {'credential_id': str(credential), 'password': catalog.secret_for(credential)})
        controller.query(resources[0], 'CREATE (:Fixture {value:42})', database='neo4j',
            user=catalog.login(cid), password=password)
        # Full-access user management is the native capability the platform fence must contain.
        controller.query(resources[0], 'ALTER USER ' + catalog.login(other) + ' SET PASSWORD $password CHANGE NOT REQUIRED',
            {'password': password}, user=catalog.login(cid), password=password)
        print('PASS dedicated instances, native writer/query and full-access account-mutation control')
        asyncio.run(relay_checks(controller, resources[0], cid, other))
    finally:
        for rid in resources:
            name, volume, network = names(rid)
            for args in [('rm', '-f', name), ('volume', 'rm', volume), ('network', 'rm', network)]:
                subprocess.run(['docker', *args], capture_output=True, timeout=60)


async def relay_checks(controller, rid, cid, other):
    # Real official cypher-shell negotiates Bolt through the actual relay.
    rows = {}
    lease = {'credential_id': str(cid), 'resource_id': str(rid), 'provider': 'neo4j',
        'native_host': controller.address(rid)['host'],
        'admission_sha256': hashlib.sha256(catalog.secret_for(cid).encode()).hexdigest(),
        'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)}
    relay = Relay(lambda: dict(rows), host='127.0.0.1')
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    # Fixture bypasses only the production allocation range; handle/guard/protocol are real.
    relay.leases[port] = lease
    relay.last_success = time.monotonic()
    server = await asyncio.start_server(lambda r,w: relay.handle(port,r,w), '127.0.0.1', port)
    name = names(rid)[0]
    async def shell(user, password, query='RETURN 1'):
        env = {**os.environ, 'NEO4J_USERNAME': user, 'NEO4J_PASSWORD': password}
        proc = await asyncio.create_subprocess_exec('docker', 'run', '--rm', '--network', 'host',
            '--memory', '256m', '--entrypoint', 'cypher-shell', '-e', 'NEO4J_USERNAME', '-e', 'NEO4J_PASSWORD',
            'neo4j:2026.09.0-community', '-a', f'bolt://127.0.0.1:{port}', '--format', 'plain', query,
            env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        # Keep the freshness clock updated without changing the fixed original deadline.
        while proc.returncode is None:
            relay.last_success = time.monotonic()
            try: return await asyncio.wait_for(proc.wait(), .25)
            except TimeoutError: pass
    try:
        assert await shell(catalog.login(cid), catalog.secret_for(cid)) == 0
        assert await shell(catalog.login(other), catalog.secret_for(cid)) != 0
        # Same native user at its own valid lease, but a password changed by another full-access user.
        mutated = {**lease, 'credential_id': str(other),
            'admission_sha256': hashlib.sha256(catalog.secret_for(other).encode()).hexdigest()}
        relay.leases[port] = mutated
        assert await shell(catalog.login(other), catalog.secret_for(cid)) != 0
        relay.leases[port] = lease
        lease['expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert await shell(catalog.login(cid), catalog.secret_for(cid)) != 0
        print('PASS native Bolt authentication, cross-lease denial, changed-password admission denial and expired reconnect')
    finally:
        relay.leases = {}
        server.close(); await server.wait_closed()


if __name__ == '__main__': main()
