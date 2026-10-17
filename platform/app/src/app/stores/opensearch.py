"""Index-scoped native OpenSearch roles, separate credential generations and TLS."""
import base64
import os
import re
from uuid import UUID
from . import catalog
from .http_client import PrivateJSON
from .s3 import StoreError


def index(resource):
    return catalog.identifier(resource['resource_id'])


def role(resource, mode):
    return index(resource) + ('_writer' if mode == 'read-write' else '_reader')


def tenant(resource):
    # Alphanumeric names survive the native tenant-index name scrub unchanged.
    return 'resource' + UUID(str(resource['resource_id'])).hex


def authorization(user, password):
    return 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()


class OpenSearch:
    def __init__(self, endpoint=None, password=None, ca_file=None):
        self.endpoint = endpoint or 'https://' + os.environ['OPENSEARCH_IP'] + ':9200'
        self.ca_file = ca_file or os.environ.get('OPENSEARCH_CA_FILE')
        if self.endpoint.startswith('https://') and not self.ca_file:
            raise StoreError('Operator-owned OpenSearch CA is required')
        self.root = PrivateJSON(self.endpoint, {'Authorization': authorization('admin',
            password or os.environ['OPENSEARCH_ADMIN_PASSWORD'])}, self.ca_file)

    def provision(self, resource):
        name = index(resource)
        self.root.request('PUT', '/_plugins/_security/api/tenants/' + tenant(resource),
            {'description': 'Named resource console workspace'})
        if self.root.request('GET', '/' + name, missing=True) is None:
            self.root.request('PUT', '/' + name, {'settings': {'number_of_shards': 1, 'number_of_replicas': 0}})
        for mode in ('read-only', 'read-write'):
            privileges = ['read', 'indices:admin/get', 'indices:admin/mappings/get',
                'indices:admin/aliases/get', 'indices:admin/resolve/index']
            if mode == 'read-write':
                privileges += ['write', 'indices:admin/mapping/put', 'indices:admin/refresh*']
            identity = role(resource, mode)
            self.root.request('PUT', '/_plugins/_security/api/roles/' + identity, {
                # Saved objects use bulk writes even for document readers. The
                # index/tenant permissions still authorize each individual item.
                'cluster_permissions': ['cluster_composite_ops_ro', 'indices:data/write/bulk'],
                'index_permissions': [{'index_patterns': [name], 'allowed_actions': privileges}],
                'tenant_permissions': [{'tenant_patterns': [tenant(resource)], 'allowed_actions': ['kibana_all_write']}]})
            self.root.request('PUT', '/_plugins/_security/api/rolesmapping/' + identity,
                {'backend_roles': [identity], 'hosts': [], 'users': []})

    def issue(self, resource, credential):
        self.root.request('PUT', '/_plugins/_security/api/internalusers/' + catalog.login(credential['credential_id']),
            {'password': catalog.secret_for(credential['credential_id']),
             'backend_roles': [role(resource, credential['mode'])], 'attributes': {}, 'opendistro_security_roles': []})
        self.verify_roles(resource, credential)

    def verify_roles(self, resource, credential):
        actual = self.scoped(credential).request('GET', '/_plugins/_security/authinfo')
        if set(actual.get('roles', [])) != {role(resource, credential['mode'])}:
            raise StoreError('Native role mapping exceeds the resource grant')
        if credential.get('kind') == 'human':
            settings = self.scoped(credential).request('GET', '/_plugins/_security/dashboardsinfo')
            if settings.get('private_tenant_enabled') is not False:
                raise StoreError('Human console access requires resource workspaces with private tenants disabled')

    def revoke(self, resource, credential):
        self.root.request('DELETE', '/_plugins/_security/api/internalusers/' + catalog.login(credential['credential_id']), missing=True)

    def credentials(self, resource, credential):
        return {'OPENSEARCH_URL': self.endpoint, 'OPENSEARCH_INDEX': index(resource),
                'OPENSEARCH_USERNAME': catalog.login(credential['credential_id']),
                'OPENSEARCH_PASSWORD': catalog.secret_for(credential['credential_id'])}

    def scoped(self, credential):
        return PrivateJSON(self.endpoint, {'Authorization': authorization(catalog.login(credential['credential_id']),
            catalog.secret_for(credential['credential_id']))}, self.ca_file)

    def probe(self, resource, credential):
        self.verify_roles(resource, credential)
        self.scoped(credential).request('GET', '/' + index(resource) + '/_search?size=0')

    def usage(self, resource):
        name = index(resource)
        value = self.root.request('GET', '/' + name + '/_stats/store')['indices'][name]['total']['store']['size_in_bytes']
        if type(value) is not int or value < 0:
            raise StoreError('Index store usage unavailable')
        return value + sum(size for _, size in self.console_indices(resource))

    def console_indices(self, resource):
        name = tenant(resource)
        rows = self.root.request('GET', '/_cat/indices/.kibana*?format=json&h=index,store.size&bytes=b&expand_wildcards=all')
        result = []
        for row in rows:
            physical = row['index']
            if name not in physical: continue
            if not re.fullmatch(r'\.kibana_-?\d+_' + name + r'(?:_[0-9]+(?:\.[0-9]+)*)*', physical):
                raise StoreError('Console index naming requires operator review')
            size = str(row.get('store.size', ''))
            if not re.fullmatch('[0-9]+', size):
                raise StoreError('Console index usage unavailable')
            result.append((physical, int(size)))
        return result

    def validate_recovery(self, resource):
        self.root.request('GET', '/' + index(resource))
        self.root.request('GET', '/_plugins/_security/api/tenants/' + tenant(resource))

    def purge(self, resource):
        for physical, _ in self.console_indices(resource):
            self.root.request('DELETE', '/' + physical, missing=True)
        self.root.request('DELETE', '/_plugins/_security/api/tenants/' + tenant(resource), missing=True)
        self.root.request('DELETE', '/' + index(resource), missing=True)
        for mode in ('read-only', 'read-write'):
            identity = role(resource, mode)
            self.root.request('DELETE', '/_plugins/_security/api/rolesmapping/' + identity, missing=True)
            self.root.request('DELETE', '/_plugins/_security/api/roles/' + identity, missing=True)
