"""Native collection RBAC with per-generation revocation and bounded JWT lifetime."""
from datetime import datetime
import os
import jwt
from . import catalog
from .http_client import PrivateJSON
from .s3 import StoreError

VALIDATION = 'platform_credential_leases'


def collection(resource):
    return catalog.identifier(resource['resource_id'])


def options(resource):
    from .contract import VectorConfiguration
    return VectorConfiguration.model_validate(resource.get('configuration') or {}).model_dump()


class Qdrant:
    quota_enforcement = 'advisory'

    def __init__(self, endpoint=None, key=None):
        self.endpoint = endpoint or 'http://' + os.environ['QDRANT_IP'] + ':6333'
        self.key = key or os.environ['QDRANT_API_KEY']
        self.root = PrivateJSON(self.endpoint, {'api-key': self.key})

    def provision(self, resource):
        config = options(resource)
        for name, vector in ((VALIDATION, {'size': 1, 'distance': 'Dot'}),
                             (collection(resource), {'size': config['vector_size'], 'distance': config['distance']})):
            if self.root.request('GET', '/collections/' + name, missing=True) is None:
                self.root.request('PUT', '/collections/' + name, {'vectors': vector, 'on_disk_payload': True})
        self.root.request('PUT', '/collections/' + VALIDATION + '/index?wait=true',
            {'field_name': 'credential_id', 'field_schema': 'keyword'})
        self.validate_recovery(resource)

    def issue(self, resource, credential):
        self.root.request('PUT', '/collections/' + VALIDATION + '/points?wait=true', {'points': [{
            'id': str(credential['credential_id']), 'vector': [1], 'payload': {
                'credential_id': str(credential['credential_id']), 'resource_id': str(resource['resource_id'])}}]})

    def token(self, resource, credential):
        expiry = credential['expires_at']
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)
        return jwt.encode({'jti': str(credential['credential_id']), 'exp': int(expiry.timestamp()),
            'access': [{'collection': collection(resource), 'access': 'rw' if credential['mode'] == 'read-write' else 'r'}],
            'value_exists': {'collection': VALIDATION, 'matches': [
                {'key': 'credential_id', 'value': str(credential['credential_id'])},
                {'key': 'resource_id', 'value': str(resource['resource_id'])}]}}, self.key, algorithm='HS256')

    def revoke(self, resource, credential):
        if self.root.request('GET', '/collections/' + VALIDATION, missing=True) is not None:
            self.root.request('POST', '/collections/' + VALIDATION + '/points/delete?wait=true',
                {'points': [str(credential['credential_id'])]})

    def credentials(self, resource, credential):
        return {'QDRANT_URL': self.endpoint, 'QDRANT_API_KEY': self.token(resource, credential),
                'QDRANT_COLLECTION': collection(resource)}

    def probe(self, resource, credential):
        PrivateJSON(self.endpoint, {'api-key': self.token(resource, credential)}).request('GET', '/collections/' + collection(resource))

    def usage(self, resource):
        memory = self.root.request('GET', '/collections/' + collection(resource) + '/memory')['result']
        # Release-specific schema verified by the real fixture. Never substitute
        # points*dimension estimates or zero for unavailable physical usage.
        value = memory['total']['disk_bytes']
        if type(value) is not int or value < 0:
            raise StoreError('Collection disk usage unavailable')
        return value

    def purge(self, resource):
        self.root.request('DELETE', '/collections/' + collection(resource), missing=True)

    def validate_recovery(self, resource):
        config = options(resource)
        actual = self.root.request('GET', '/collections/' + collection(resource))['result']['config']['params']['vectors']
        if actual['size'] != config['vector_size'] or actual['distance'] != config['distance']:
            raise StoreError('Retained vector schema differs from its resource declaration')
