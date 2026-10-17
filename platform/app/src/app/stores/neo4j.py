"""Dedicated Community instances; the operator controller alone owns Docker."""
import hashlib
import ipaddress
import os
from uuid import UUID
from . import catalog
from .http_client import PrivateJSON
from .s3 import StoreError

IMAGE = 'neo4j:2026.09.0-community@sha256:d6269a020149934597c8c3df926d080a612796dbbb48861ca9d5b1109cabf0d8'


def require_mode(provider, mode):
    if provider == 'neo4j' and mode != 'read-write':
        raise catalog.Conflict('Neo4j Community supports full instance access only; read-only is unsupported')


def admission(password, lease):
    """Native admins may change users; they cannot forge the platform secret."""
    import hmac
    expected = lease.get('admission_sha256', '')
    if not expected or not hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), expected):
        raise ValueError('Platform credential mismatch')


class Neo4j:
    quota_enforcement = 'advisory'

    def __init__(self, endpoint=None, key=None):
        host = str(ipaddress.IPv4Address(os.environ.get('NEO4J_CONTROLLER_IP', '172.30.80.31')))
        self.root = PrivateJSON(endpoint or f'http://{host}:8091',
            {'Authorization': 'Bearer ' + (key or os.environ['NEO4J_CONTROLLER_KEY'])})

    def call(self, action, resource, **values):
        return self.root.request('POST', '/v1/instances/' + str(UUID(str(resource['resource_id']))) + '/' + action, values)

    def provision(self, resource):
        return self.call('ensure', resource)

    def retire(self, resource):
        self.call('retire', resource)

    def issue(self, resource, credential):
        require_mode('neo4j', credential['mode'])
        self.call('issue', resource, credential_id=str(UUID(str(credential['credential_id']))),
            password=catalog.secret_for(credential['credential_id']))

    def revoke(self, resource, credential):
        self.call('revoke', resource, credential_id=str(UUID(str(credential['credential_id']))))

    def probe(self, resource, credential):
        self.call('probe', resource, credential_id=str(UUID(str(credential['credential_id']))),
            password=catalog.secret_for(credential['credential_id']))

    def credentials(self, resource, credential):
        return {'NEO4J_URI': '', 'NEO4J_USERNAME': catalog.login(credential['credential_id']),
            'NEO4J_PASSWORD': catalog.secret_for(credential['credential_id']), 'NEO4J_DATABASE': 'neo4j'}

    def usage(self, resource):
        value = self.call('usage', resource)['used_bytes']
        if type(value) is not int or value < 0: raise StoreError('Instance disk usage unavailable')
        return value

    def purge(self, resource):
        self.call('purge', resource)

    def validate_recovery(self, resource):
        self.call('probe', resource)
