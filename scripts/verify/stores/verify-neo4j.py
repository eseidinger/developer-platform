#!/usr/bin/env python3
"""Disposable Community identity/protocol/isolation fixture; never logs native errors."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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
from app.stores.neo4j import IMAGE
from app.stores import catalog
from app.stores.relay import Relay


def command(*args):
    result = subprocess.run(args, capture_output=True, timeout=90)
    if result.returncode: raise RuntimeError('Disposable Neo4j command failed')
    return result.stdout


def main():
    os.environ.update(NEO4J_CONTROLLER_KEY=secrets.token_hex(32), NEO4J_ADMIN_KEY=secrets.token_hex(32), DATABASE_KEY=secrets.token_hex(32),
        NEO4J_INSTANCE_PREFIX='fixture-neo4j-' + uuid4().hex[:8] + '-', NEO4J_NETWORK_MEMBERS='')
    controller = Controller()
    resources = [uuid4(), uuid4()]
    try:
        if os.environ.get('NEO4J_BROWSER_ONLY')=='1':
            from app.stores.neo4j import Neo4j
            from scripts.fixtures.store_http_console_fixture import run
            class Native(Neo4j):
                def __init__(self):pass
                def call(self,action,resource,**values):return controller.apply(resource['resource_id'],action,values)
            asyncio.run(run({'neo4j':Native()},{},{}))
            return
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
        values=controller.apply(resources[0],'jvm',{})
        assert values['platform_jvm_heap_used_bytes']>0 and values['platform_jvm_heap_max_bytes']>0
        assert values['platform_jvm_gc_seconds_total']>=0 and values['platform_jvm_threads']>0
        print('PASS Community standard JVM heap/GC metrics without Enterprise features')
        cid, other = uuid4(), uuid4()
        password = catalog.secret_for(cid)
        for credential in (cid, other):
            controller.apply(resources[0], 'issue', {'credential_id': str(credential), 'password': catalog.secret_for(credential)})
        controller.query(resources[0], 'CREATE (:Fixture {value:42})', database='neo4j',
            user=catalog.login(cid), password=password)
        controller.query(resources[0],'CREATE CONSTRAINT fixture_value IF NOT EXISTS FOR (n:Fixture) REQUIRE n.value IS UNIQUE',
            database='neo4j',user=catalog.login(cid),password=password)
        controller.query(resources[0],'DROP CONSTRAINT fixture_value IF EXISTS',database='neo4j',user=catalog.login(cid),password=password)
        # Full-access user management is the native capability the platform fence must contain.
        controller.query(resources[0], 'ALTER USER ' + catalog.login(other) + ' SET PASSWORD $password CHANGE NOT REQUIRED',
            {'password': password}, user=catalog.login(cid), password=password)
        print('PASS dedicated instances, native writer/query and full-access account-mutation control')
        asyncio.run(relay_checks(controller, resources[0], cid, other))
        asyncio.run(held_checks(controller,resources[0],cid))
        recovery_check(controller,resources[0],cid)

        for _ in range(120):
            try:
                controller.query(resources[0],'RETURN 1',database='neo4j');break
            except Exception:time.sleep(.5)
        else:raise AssertionError('Original instance did not recover after offline capture')
        def tcp(container,host):
            try:return subprocess.run(['docker','exec',container,'bash','-c','exec 3<>/dev/tcp/'+host+'/7687'],capture_output=True,timeout=3).returncode
            except subprocess.TimeoutExpired:return -1
        assert tcp(names(resources[0])[0],'127.0.0.1')==0
        assert tcp(names(resources[1])[0],'127.0.0.1')==0
        assert tcp(names(resources[0])[0],controller.address(resources[1])['host'])!=0
        print('PASS private instance network blocks cross-instance native TCP with healthy-listener positive controls')
        if os.environ.get('NEO4J_CONSOLE_FIXTURE') == '1':
            from app.stores.neo4j import Neo4j
            from scripts.fixtures.store_http_console_fixture import run
            class Native(Neo4j):
                def __init__(self): pass
                def call(self, action, resource, **values): return controller.apply(resource['resource_id'],action,values)
            asyncio.run(run({'neo4j':Native()}, {}, {}))
        # Full-access users can damage native administration; stop/purge fencing
        # remains available without a native administrator login.
        native_env={**os.environ,'NEO4J_USERNAME':catalog.login(cid),'NEO4J_PASSWORD':password}
        changed=subprocess.run(['docker','run','--rm','-i','--network','container:'+names(resources[0])[0],
            '--memory','256m','--cpus','1','--entrypoint','cypher-shell','-e','NEO4J_USERNAME','-e','NEO4J_PASSWORD',
            IMAGE,'-a','bolt://127.0.0.1:7687','--format','plain'],env=native_env,
            input='ALTER USER neo4j SET PASSWORD \''+secrets.token_hex(32)+'\' CHANGE NOT REQUIRED;\n',
            text=True,capture_output=True,timeout=30)
        assert changed.returncode==0,'Native full-access administrator mutation failed'
        for _ in range(30):
            try:
                controller.apply(resources[0],'retire',{});break
            except Exception:time.sleep(.5)
        else:raise AssertionError('Dedicated retirement did not finish')
        controller.apply(resources[0],'retire',{})
        assert not controller.info(resources[0])['State']['Running']
        assert controller.apply(resources[0],'usage',{})['used_bytes']>0
        controller.apply(resources[0],'purge',{})
        controller.apply(resources[0],'purge',{})
        assert controller.info(resources[0]) is None
        assert controller.engine.call('GET','/volumes/'+names(resources[0])[1],missing=True) is None
        assert controller.engine.call('GET','/networks/'+names(resources[0])[2],missing=True) is None
        controller.query(resources[1],'RETURN 1',database='neo4j')
        print('PASS retained retirement and idempotent isolated volume/network purge, including changed native administrator password')


    finally:
        for item in controller.engine.call('GET','/containers/json?all=1'):
            if item['Names'][0].lstrip('/').startswith(os.environ['NEO4J_INSTANCE_PREFIX']):
                from uuid import UUID
                rid=UUID(item['Labels']['developer-platform.neo4j-resource'])
                if rid not in resources: resources.append(rid)
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
            IMAGE, '-a', f'bolt://127.0.0.1:{port}', '--format', 'plain', query,
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


async def held_checks(controller,rid,cid):
    from app.stores.bolt_relay import message,Decoder
    def pack(value):
        if isinstance(value,str):
            data=value.encode();return (bytes([0x80+len(data)]) if len(data)<16 else b'\xd0'+bytes([len(data)]))+data
        if isinstance(value,dict):return bytes([0xa0+len(value)])+b''.join(pack(k)+pack(v) for k,v in value.items())
        raise ValueError()
    def frame(tag,value):
        body=bytes([0xb1,tag])+pack(value)
        return len(body).to_bytes(2,'big')+body+b'\0\0'
    relay=Relay(host='127.0.0.1')
    async def handle(reader,writer):await relay.handle(port,reader,writer)
    server=await asyncio.start_server(handle,'127.0.0.1',0)
    port=server.sockets[0].getsockname()[1]
    password=catalog.secret_for(cid)
    async def fresh_clock():
        while True:relay.last_success=time.monotonic();await asyncio.sleep(.05)
    ticking=asyncio.create_task(fresh_clock())
    try:
        for action in ('expire','revoke','catalog-outage'):
            lease={'credential_id':str(cid),'resource_id':str(rid),'provider':'neo4j',
                'native_host':controller.address(rid)['host'],
                'admission_sha256':hashlib.sha256(password.encode()).hexdigest(),
                'expires_at':datetime.now(timezone.utc)+timedelta(seconds=10)}
            relay.leases={port:dict(lease)};relay.last_success=time.monotonic()
            reader,writer=await asyncio.open_connection('127.0.0.1',port)
            writer.write(b'\x60\x60\xb0\x17'+b'\0\0\x04\x05'+b'\0'*12);await writer.drain()
            assert await reader.readexactly(4)==b'\0\0\x04\x05'
            for tag,value in [(1,{'user_agent':'platform-fixture','bolt_agent':{'product':'platform-fixture'}}),(0x6a,{'scheme':'basic','principal':catalog.login(cid),'credentials':password})]:
                writer.write(frame(tag,value));await writer.drain()
                data,_=await asyncio.wait_for(message(reader),3)
                response=Decoder(data).value()
                if response[0]!=0x70:
                    import re
                    codes=[value for metadata in response[1] if isinstance(metadata,dict) for key,value in metadata.items()
                        if key in {'code','neo4j_code'} and isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.]+',value)]
                    print('Held-session protocol phase/tag/error codes:',tag,response[0],codes)
                    raise AssertionError('Native held-session authentication failed')
            if action=='expire':relay.leases[port]['expires_at']=datetime.now(timezone.utc)+timedelta(milliseconds=100)
            elif action=='revoke':relay.leases={}
            else:
                ticking.cancel();await asyncio.gather(ticking,return_exceptions=True)
                relay.last_success=time.monotonic()-10
            assert await asyncio.wait_for(reader.read(1),1)==b''
            writer.close();await writer.wait_closed()
            # The native key remains valid, proving the independent outer fence.
            controller.query(rid,'RETURN 1',database='neo4j',user=catalog.login(cid),password=password)
        print('PASS authenticated held Bolt sockets close on expiry, revocation and stale catalog; native-key positive controls remain valid')
    finally:
        ticking.cancel();await asyncio.gather(ticking,return_exceptions=True)
        relay.leases={};server.close();await server.wait_closed()


def recovery_check(controller,rid,cid):
    from scripts.fixtures.store_volume_fixture import restored
    from app.stores.neo4j import IMAGE
    from app.stores.http_client import PrivateJSON
    import base64
    name,volume,_=names(rid)
    env={**os.environ,'NEO4J_AUTH':'neo4j/'+controller.password(rid)}
    arguments=['--user','7474:7474','--memory','1536m','--cpus','1','--tmpfs','/logs:rw,size=64m,uid=7474,gid=7474',
        '--tmpfs','/tmp:rw,size=256m,mode=1777','-e','NEO4J_AUTH','-e','NEO4J_server_memory_heap_initial__size=256m',
        '-e','NEO4J_server_memory_heap_max__size=512m','-e','NEO4J_server_memory_pagecache_size=256m','-p','127.0.0.1::7474']
    with restored(name,volume,'/data',IMAGE,arguments,env) as recovered:
        port=int(command('docker','port',recovered,'7474/tcp').decode().strip().rsplit(':',1)[1])
        def client(user,password):return PrivateJSON(f'http://127.0.0.1:{port}',{'Authorization':'Basic '+base64.b64encode((user+':'+password).encode()).decode()})
        admin=client('neo4j',controller.password(rid))
        for _ in range(120):
            try:
                admin.request('POST','/db/neo4j/query/v2',{'statement':'RETURN 1'});break
            except Exception:time.sleep(.5)
        else:raise AssertionError('Restored Community instance unavailable')
        old=client(catalog.login(cid),catalog.secret_for(cid))
        data=old.request('POST','/db/neo4j/query/v2',{'statement':'MATCH (n:Fixture) RETURN n.value'})
        assert data['data']['values']==[[42]]
        admin.request('POST','/db/system/query/v2',{'statement':'DROP USER '+catalog.login(cid)+' IF EXISTS'})
        fresh=uuid4()
        admin.request('POST','/db/system/query/v2',{'statement':'CREATE USER '+catalog.login(fresh)+' SET PASSWORD $password CHANGE NOT REQUIRED','parameters':{'password':catalog.secret_for(fresh)}})
        result=client(catalog.login(fresh),catalog.secret_for(fresh)).request('POST','/db/neo4j/query/v2',{'statement':'MATCH (n:Fixture) RETURN n.value'})
        assert result['data']['values']==[[42]]
        from app.stores.s3 import StoreError
        try:old.request('POST','/db/neo4j/query/v2',{'statement':'RETURN 1'})
        except StoreError:pass
        else:raise AssertionError('Recovered revoked native credential remained usable')
        print('PASS stopped Community volume restored into an empty volume; data/system identities retained, old identity revoked and fresh approval queried retained graph')


if __name__ == '__main__': main()
