"""Narrow operator-only Docker controller. Never run inside the API/relay.

No arbitrary image, mount, command, network or Cypher is accepted from requests.
Daemon errors, native payloads and passwords are never logged or returned.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import threading
import time
from uuid import UUID
import httpx2 as httpx
from fastapi import FastAPI, Request, HTTPException
from .neo4j import IMAGE
from . import catalog

LABEL = 'developer-platform.neo4j-resource'
LOCK = threading.Lock()
DEADLINE = threading.local()

def remaining():
    value = getattr(DEADLINE, "until", time.monotonic()+5)-time.monotonic()
    if value<=0: raise ValueError("Operator request deadline exceeded")
    return min(5,value)


class Engine:
    def __init__(self):
        self.client = httpx.Client(transport=httpx.HTTPTransport(uds='/var/run/docker.sock'),
            base_url='http://docker', timeout=5, trust_env=False)

    def call(self, method, path, body=None, missing=False):
        r = self.client.request(method, '/v1.47' + path, json=body,timeout=remaining())
        if missing and r.status_code == 404: return None
        if r.status_code >= 400: raise ValueError('Operator daemon operation unavailable')
        return r.json() if r.content else {}


def names(resource):
    suffix = UUID(str(resource)).hex
    prefix = os.environ.get('NEO4J_INSTANCE_PREFIX', 'platform-neo4j-')
    if not prefix.replace('-', '').isalnum() or len(prefix) > 50: raise ValueError()
    return prefix + suffix, prefix + suffix + '-data', prefix + suffix + '-private'


class Controller:
    def __init__(self, engine=None):
        self.engine = engine or Engine()

    def info(self, rid):
        name, _, _ = names(rid)
        value = self.engine.call('GET', '/containers/' + name + '/json', missing=True)
        if value and (value['Config']['Labels'].get(LABEL) != str(rid)
                      or value['Config']['Image'] != IMAGE):
            raise ValueError('Instance identity or image differs; operator review required')
        return value

    def password(self, rid):
        return hmac.new(os.environ['NEO4J_ADMIN_KEY'].encode(),
            ('neo4j-admin-v1:' + str(rid)).encode(), hashlib.sha256).hexdigest()

    def ensure(self, rid):
        name, volume, network = names(rid)
        info = self.info(rid)
        if info is None:
            instances = self.engine.call('GET', '/containers/json?all=1')
            if sum(LABEL in item.get('Labels', {}) for item in instances) >= int(os.environ.get('NEO4J_MAX_INSTANCES', '4')):
                raise ValueError('Operator instance allocation exhausted')
            labels = {LABEL: str(rid)}
            if self.engine.call('GET', '/networks/' + network, missing=True) is None:
                self.engine.call('POST', '/networks/create', {'Name': network, 'Internal': True, 'Labels': labels})
            existing_volume = self.engine.call('GET', '/volumes/' + volume, missing=True)
            if existing_volume is None:
                self.engine.call('POST', '/volumes/create', {'Name': volume, 'Labels': labels})
            elif existing_volume.get('Labels', {}).get(LABEL) != str(rid):
                raise ValueError('Volume ownership mismatch')
            self.engine.call('POST', '/containers/create?name=' + name, {
                'Image': IMAGE, 'Labels': labels, 'User': '7474:7474',
                'Env': ['NEO4J_AUTH=neo4j/' + self.password(rid),
                    'NEO4J_server_jvm_additional=-javaagent:/opt/platform/jmx-agent.jar=9404:/opt/platform/jmx.yaml',
                    'NEO4J_server_memory_heap_initial__size=256m', 'NEO4J_server_memory_heap_max__size=512m',
                    'NEO4J_server_memory_pagecache_size=256m', 'NEO4J_server_bolt_tls__level=DISABLED',
                    'NEO4J_dbms_security_allow__csv__import__from__file__urls=false',
                    'NEO4J_dbms_security_procedures_unrestricted=', 'NEO4J_dbms_usage__report_enabled=false'],
                'HostConfig': {'NetworkMode': network, 'Memory': int(os.environ.get('NEO4J_INSTANCE_MEMORY_BYTES', '1610612736')),
                    'NanoCpus': 1000000000, 'PidsLimit': 256, 'CapDrop': ['ALL'],
                    'SecurityOpt': ['no-new-privileges:true'], 'RestartPolicy': {'Name': 'unless-stopped'},
                    'Mounts': [{'Type': 'volume', 'Source': volume, 'Target': '/data'}],
                    'Tmpfs': {'/logs': 'rw,size=64m,uid=7474,gid=7474', '/tmp': 'rw,size=256m,mode=1777'}},
                'NetworkingConfig': {'EndpointsConfig': {network: {}}}})
            info = self.info(rid)
        net = self.engine.call('GET', '/networks/' + network)
        if net.get('Labels', {}).get(LABEL) != str(rid) or not net.get('Internal'):
            raise ValueError('Network ownership mismatch')
        # Only reviewed infrastructure containers join the private instance network.
        for member in os.environ.get('NEO4J_NETWORK_MEMBERS', 'developer-platform-neo4j-controller-1,developer-platform-platform-api-1,developer-platform-store-access-1').split(','):
            if not member: continue
            member_info = self.engine.call('GET', '/containers/' + member + '/json')
            if network not in member_info['NetworkSettings']['Networks']:
                self.engine.call('POST', '/networks/' + network + '/connect', {'Container': member})
        if not info['State']['Running']:
            self.engine.call('POST', '/containers/' + name + '/start')
        return self.address(rid)

    def address(self, rid):
        info = self.info(rid)
        if not info or not info['State']['Running']: raise ValueError('Instance not running')
        host = str(ipaddress.IPv4Address(info['NetworkSettings']['Networks'][names(rid)[2]]['IPAddress']))
        return {'host': host, 'port': 7687}

    def query(self, rid, statement, parameters=None, database='system', user=None, password=None):
        host = self.address(rid)['host']
        with httpx.Client(timeout=min(3,remaining()), trust_env=False, follow_redirects=False) as client:
            response = client.post(f'http://{host}:7474/db/{database}/query/v2',
                auth=(user or 'neo4j', password or self.password(rid)),
                json={'statement': statement, 'parameters': parameters or {}})
        if response.status_code >= 400 or len(response.content) > 262144: raise ValueError('Native operation failed')
        value = response.json()
        if value.get('errors'): raise ValueError('Native operation failed')
        return value

    def purge_network(self,rid,info,apply=False):
        network=names(rid)[2]
        value=self.engine.call('GET','/networks/'+network,missing=True)
        if value is None:return
        if value.get('Labels',{}).get(LABEL)!=str(rid) or not value.get('Internal'):raise ValueError('Network ownership mismatch')
        allowed={info['Id']} if info else set()
        for member in os.environ.get('NEO4J_NETWORK_MEMBERS','developer-platform-neo4j-controller-1,developer-platform-platform-api-1,developer-platform-store-access-1').split(','):
            if not member:continue
            member_info=self.engine.call('GET','/containers/'+member+'/json',missing=True)
            if member_info:allowed.add(member_info['Id'])
        if set(value.get('Containers',{}))-allowed:raise ValueError('Unexpected dedicated network member')
        if apply:
            for member in value.get('Containers',{}):
                self.engine.call('POST','/networks/'+network+'/disconnect',{'Container':member,'Force':True})
            self.engine.call('DELETE','/networks/'+network)

    def container_metrics(self):
        services = {'postgres':'postgresql','rustfs':'s3','opensearch':'opensearch','qdrant':'qdrant'}
        result = []
        for item in self.engine.call('GET', '/containers/json?all=1'):
            labels = item.get('Labels') or {}
            resource = labels.get(LABEL)
            if resource:
                resource = str(UUID(resource))
                provider = 'neo4j'
            elif labels.get('com.docker.compose.project') == 'developer-platform':
                provider = services.get(labels.get('com.docker.compose.service'))
            else: continue
            if not provider: continue
            info = self.engine.call('GET', '/containers/' + item['Id'] + '/json')
            values = {'provider': provider, 'resource_id': resource, 'running': int(info['State']['Running']),
                'restarts': info.get('RestartCount', 0)}
            if info['State']['Running']:
                stats = self.engine.call('GET', '/containers/' + item['Id'] + '/stats?stream=false&one-shot=true')
                memory = stats['memory_stats']
                values.update(cpu_seconds_total=stats['cpu_stats']['cpu_usage']['total_usage']/1e9,
                    memory_bytes=max(0, memory['usage'] - memory.get('stats', {}).get('inactive_file', 0)),
                    memory_limit_bytes=memory['limit'], cpu_limit_cores=info['HostConfig'].get('NanoCpus', 0)/1e9)
                io = stats.get('blkio_stats', {}).get('io_service_bytes_recursive') or []
                for operation in ('read','write'):
                    values[operation + '_bytes_total'] = sum(row['value'] for row in io if row['op'].lower() == operation)
            result.append(values)
            if len(result) > 132: raise ValueError('Container inventory limit')
        return result

    def apply(self, rid, action, values):
        rid = UUID(str(rid))
        if action == 'containers': return {'containers': self.container_metrics()}
        if 'neo4j' not in os.environ.get('STORE_ENABLED_PROVIDERS', 'neo4j').split(','): raise ValueError('Neo4j not selected')
        if action == 'ensure':
            result = self.ensure(rid)
            self.query(rid, 'RETURN 1', database='neo4j')
            return result
        info = self.info(rid)
        if action in {'retire', 'purge'}:
            if action=='purge':self.purge_network(rid,info)
            if info and info['State']['Running']:
                self.engine.call('POST', '/containers/' + names(rid)[0] + '/stop?t=30')
            if action == 'purge':
                if info: self.engine.call('DELETE', '/containers/' + names(rid)[0])
                volume = self.engine.call('GET', '/volumes/' + names(rid)[1], missing=True)
                if volume:
                    if volume.get('Labels', {}).get(LABEL) != str(rid): raise ValueError('Volume ownership mismatch')
                    self.engine.call('DELETE', '/volumes/' + names(rid)[1])
                self.purge_network(rid,None,apply=True)
            return {}
        if info is None:
            if action == 'revoke': return {}
            raise ValueError('Instance unavailable')
        if action in {'issue', 'revoke', 'probe'}:
            if values.get('credential_id'):
                user = catalog.login(UUID(values['credential_id']))
                if action == 'revoke':
                    self.query(rid, 'DROP USER ' + user + ' IF EXISTS')
                else:
                    password = values['password']
                    if len(password) != 64 or any(c not in '0123456789abcdef' for c in password): raise ValueError()
                    if action == 'issue':
                        self.query(rid, 'CREATE OR REPLACE USER ' + user + ' SET PASSWORD $password CHANGE NOT REQUIRED', {'password': password})
                    self.query(rid, 'RETURN 1', database='neo4j', user=user, password=password)
            else:
                if action != 'probe': raise ValueError()
                self.query(rid, 'RETURN 1', database='neo4j')
            return {}
        if action == 'jvm':
            host = self.address(rid)['host']
            with httpx.Client(timeout=3,trust_env=False) as client:
                response=client.get(f'http://{host}:9404/metrics')
            if response.status_code!=200 or len(response.content)>262144: raise ValueError()
            import re
            values={}
            for item in response.text.splitlines():
                matched=re.fullmatch(r'(platform_jvm_heap_(?:used|max|committed)_bytes|platform_jvm_gc_seconds_total|platform_jvm_threads)(?:\{[^}]*\})? ([0-9.eE+\-]+)',item)
                if matched:
                    values[matched[1]]=values.get(matched[1],0)+float(matched[2])
            if not {'platform_jvm_heap_used_bytes','platform_jvm_heap_max_bytes'} <= values.keys(): raise ValueError('JVM metrics unavailable')
            return values
        if action == 'usage':
            for volume in self.engine.call('GET','/system/df').get('Volumes',[]):
                if volume['Name']==names(rid)[1] and volume.get('Labels',{}).get(LABEL)==str(rid):
                    value=volume.get('UsageData',{}).get('Size')
                    if type(value) is not int or value<0: raise ValueError()
                    return {'used_bytes':value}
            raise ValueError('Retained volume usage unavailable')
        raise ValueError('Unsupported operation')


def create_app(controller=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    for name in ('NEO4J_CONTROLLER_KEY','NEO4J_ADMIN_KEY'):
        if len(os.environ.get(name,''))<32:raise ValueError('Operator controller secret configuration unavailable')
    maximum=int(os.environ.get('NEO4J_MAX_INSTANCES','4'))
    memory=int(os.environ.get('NEO4J_INSTANCE_MEMORY_BYTES','1610612736'))
    if not 1<=maximum<=64 or not 1073741824<=memory<=17179869184:raise ValueError('Operator instance allocation invalid')
    control = controller or Controller()

    @app.post('/v1/instances/{rid}/{action}')
    async def operation(rid: UUID, action: str, request: Request):
        received=time.monotonic()
        key = os.environ.get('NEO4J_CONTROLLER_KEY', '')
        if (len(key) < 32 or not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + key)
                or request.client.host != os.environ.get('PLATFORM_API_IP', '172.30.80.11')):
            raise HTTPException(403)
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 4096: raise HTTPException(413)
        try:
            values = json.loads(payload or b'{}')
            if not isinstance(values, dict) or set(values) - {'credential_id', 'password'}: raise ValueError()
            import asyncio
            def apply():
                with LOCK:
                    DEADLINE.until=received+4
                    try:
                        remaining()  # Stale queued calls cannot mutate after their caller timed out.
                        return control.apply(rid, action, values)
                    finally: del DEADLINE.until
            return await asyncio.to_thread(apply)
        except Exception:
            raise HTTPException(503, 'Dedicated instance operation unavailable') from None
    return app
