#!/usr/bin/env python3
"""Disposable native Security-plugin scope and search acceptance, not deployed TLS."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
import json
import re
import secrets
import subprocess
import time
from unittest.mock import patch
from uuid import uuid4

import httpx
from app.stores.opensearch import OpenSearch, index, tenant, authorization
from app.stores.http_client import PrivateJSON
from app.stores.relay import Relay
from app.stores import catalog
from app.stores.s3 import StoreError
from store_volume_fixture import restored

IMAGE = 'opensearchproject/opensearch:3.9.0@sha256:adfa61f85025d06b4aeb562e7e74fde7e31c437039c93c3862c17e9acebd6c7c'


def command(*arguments, env=None):
    result = subprocess.run(arguments, capture_output=True, timeout=60, env=env)
    if result.returncode:
        raise RuntimeError('Disposable OpenSearch command failed')
    return result.stdout.decode().strip()


def denied(operation):
    try:
        operation()
    except StoreError as error:
        assert str(error) in {'Provider request failed (401)', 'Provider request failed (403)'}, str(error)
    else:
        raise AssertionError('Scoped search credential exceeded its permissions')


def main():
    name = 'named-search-' + uuid4().hex[:12]
    volume = name + '-data'
    password = 'Aa9!' + secrets.token_hex(32)
    os.environ['DATABASE_KEY'] = secrets.token_hex(32)
    os.environ['STORE_MONITOR_PASSWORD'] = 'Aa9!' + secrets.token_hex(32)
    env = {**os.environ, 'OPENSEARCH_INITIAL_ADMIN_PASSWORD': password}
    try:
        # The image's demo certificates are used only for internal transport in
        # this loopback-only fixture. Production requires an operator-owned CA.
        command('docker', 'run', '-d', '--name', name, '--memory', '1536m', '--cpus', '1',
            '--mount', f'type=volume,src={volume},dst=/usr/share/opensearch/data',
            '-e', 'OPENSEARCH_INITIAL_ADMIN_PASSWORD', '-e', 'discovery.type=single-node',
            '-e', 'OPENSEARCH_JAVA_OPTS=-Xms256m -Xmx256m', '-e', 'node.store.allow_mmap=false',
            '-e', 'plugins.security.ssl.http.enabled=false', '-p', '127.0.0.1::9200', IMAGE, env=env)
        port = int(command('docker', 'port', name, '9200/tcp').rsplit(':', 1)[1])
        endpoint = f'http://127.0.0.1:{port}'
        provider = OpenSearch(endpoint, password)
        for _ in range(120):
            try:
                provider.root.request('GET', '/_cluster/health')
                break
            except Exception:
                time.sleep(.4)
        else:
            # Fixed diagnostics only: container logs may include credentials.
            raise AssertionError('Disposable OpenSearch did not become ready')
        first, other = ({'resource_id': str(uuid4())} for _ in range(2))
        for resource in (first, other):
            provider.provision(resource)
            provider.provision(resource)
        credentials = []
        for mode in ('read-write', 'read-only'):
            credential = {'credential_id': str(uuid4()), 'mode': mode,
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            provider.issue(first, credential)
            provider.issue(first, credential)
            provider.probe(first, credential)
            credentials.append(credential)
        from app.stores.native_monitoring import opensearch as native_metrics
        output = native_metrics(provider, [{**first, 'state':'active','owner_project':'fixture'}, {**other,'state':'active','owner_project':'other'}])
        assert any('platform_native_opensearch_heap_used_bytes' in item for item in output)
        assert any('platform_native_opensearch_search_total' in item for item in output)
        from app.stores.opensearch import authorization as native_authorization
        monitor = PrivateJSON(endpoint, {'Authorization': native_authorization('platform_monitor', os.environ['STORE_MONITOR_PASSWORD'])})
        denied(lambda: monitor.request('GET', '/' + index(first) + '/_search'))
        denied(lambda: monitor.request('PUT', '/_plugins/_security/api/internalusers/not-allowed', {'password':'Aa9!'+secrets.token_hex(32)}))
        print('PASS restricted native statistics collection and data/identity administration denial')
        writer, reader = credentials
        rw, ro = provider.scoped(writer), provider.scoped(reader)
        prefix, foreign = '/' + index(first), '/' + index(other)
        rw.request('PUT', prefix + '/_mapping', {'properties': {'title': {'type': 'text'}, 'kind': {'type': 'keyword'}}})
        rw.request('PUT', prefix + '/_doc/one?refresh=true', {'title': 'renewable energy dataset', 'kind': 'reviewed'})
        rw.request('PUT', prefix + '/_doc/two?refresh=true', {'title': 'unrelated fixture', 'kind': 'other'})
        result = ro.request('POST', prefix + '/_search', {'query': {'bool': {
            'must': [{'match': {'title': 'energy'}}], 'filter': [{'term': {'kind': 'reviewed'}}]}},
            'aggs': {'kinds': {'terms': {'field': 'kind'}}}})
        assert result['hits']['hits'][0]['_id'] == 'one'
        denied(lambda: ro.request('PUT', prefix + '/_doc/three', {'title': 'denied'}))
        denied(lambda: ro.request('PUT', prefix + '/_mapping', {'properties': {'denied': {'type': 'keyword'}}}))
        reader_bulk = httpx.post(endpoint + '/_bulk', content=json.dumps({'index': {'_index': index(first), '_id': 'reader-denied'}})
            + '\n' + json.dumps({'title': 'denied'}) + '\n', headers={
                'Authorization': authorization(catalog.login(reader['credential_id']), catalog.secret_for(reader['credential_id'])),
                'Content-Type': 'application/x-ndjson'}).json()
        assert reader_bulk['errors'] and reader_bulk['items'][0]['index']['status'] == 403
        denied(lambda: rw.request('GET', foreign + '/_search'))
        assert index(first) in ro.request('GET', prefix + '/_alias')
        denied(lambda: ro.request('GET', foreign + '/_alias'))
        assert ro.request('GET', '/_resolve/index/' + index(first))['indices'][0]['name'] == index(first)
        denied(lambda: ro.request('GET', '/_resolve/index/' + index(other)))
        try:
            visible = ro.request('GET', '/_resolve/index/*?expand_wildcards=all')
        except StoreError as error:
            assert '(403)' in str(error)
        else:
            assert index(other) not in {value['name'] for value in visible['indices']}, 'Wildcard metadata exposed a foreign resource'
        denied(lambda: rw.request('POST', '/_aliases', {'actions': [{'add': {'index': index(first), 'alias': index(first) + '-alias'}}]}))
        denied(lambda: rw.request('DELETE', prefix))
        denied(lambda: rw.request('PUT', prefix + '/_settings', {'index.blocks.write': False}))
        denied(lambda: rw.request('PUT', '/rogue', {}))
        denied(lambda: rw.request('PUT', '/' + catalog.login(writer['credential_id']), {}))
        denied(lambda: rw.request('GET', '/_plugins/_security/api/internalusers'))
        denied(lambda: rw.request('PUT', '/_plugins/_security/api/internalusers/' + catalog.login(writer['credential_id']),
            {'password': 'Aa9!synthetic-replacement', 'backend_roles': ['all_access']}))
        denied(lambda: rw.request('POST', '/_aliases', {'actions': [{'add': {'index': index(other), 'alias': index(first) + '-foreign'}}]}))
        mixed = '\n'.join(json.dumps(item) for item in [
            {'index': {'_index': index(first), '_id': 'own-bulk'}}, {'title': 'authorized bulk'},
            {'index': {'_index': index(other), '_id': 'foreign-bulk'}}, {'title': 'forbidden bulk'}]) + '\n'
        with httpx.Client(trust_env=False) as http:
            bulk = http.post(endpoint + '/_bulk', content=mixed, headers={
                'Authorization': authorization(catalog.login(writer['credential_id']), catalog.secret_for(writer['credential_id'])),
                'Content-Type': 'application/x-ndjson'}).json()
        assert bulk['errors'] and bulk['items'][0]['index']['status'] in {200, 201}
        assert bulk['items'][1]['index']['status'] == 403
        def workspace(native, resource, credential):
            return PrivateJSON(native.endpoint, {'Authorization': authorization(catalog.login(credential['credential_id']),
                catalog.secret_for(credential['credential_id'])), 'securitytenant': tenant(resource)}, native.ca_file)
        # Store readers can manage visualization metadata in this resource's
        # workspace, while the existing document/mapping write denials remain.
        try:
            workspace(provider, first, reader).request('PUT', '/.kibana/_doc/fixture?refresh=true', {'title': 'retained workspace'})
        except StoreError:
            result = httpx.put(endpoint + '/.kibana/_doc/fixture?refresh=true', headers={
                'Authorization': authorization(catalog.login(reader['credential_id']), catalog.secret_for(reader['credential_id'])),
                'securitytenant': tenant(first)}, json={'title': 'retained workspace'})
            action = re.search(r'no permissions for \[((?:indices|cluster):[a-z:_/*]+)', result.text)
            print('Native workspace denied action: ' + (action[1] if action else 'unclassified'))
            raise
        other_reader = {'credential_id': str(uuid4()), 'mode': 'read-only',
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
        provider.issue(other, other_reader)
        workspace(provider, other, other_reader).request('PUT', '/.kibana/_doc/fixture?refresh=true', {'title': 'other workspace'})
        denied(lambda: workspace(provider, other, reader).request('GET', '/.kibana/_doc/fixture'))
        assert provider.console_indices(first) and provider.console_indices(other)
        assert provider.usage(first) > 0
        with restored(name, volume, '/usr/share/opensearch/data', IMAGE, ['--memory', '1536m', '--cpus', '1',
                '-e', 'OPENSEARCH_INITIAL_ADMIN_PASSWORD', '-e', 'discovery.type=single-node',
                '-e', 'OPENSEARCH_JAVA_OPTS=-Xms256m -Xmx256m', '-e', 'node.store.allow_mmap=false',
                '-e', 'plugins.security.ssl.http.enabled=false', '-p', '127.0.0.1::9200'], env) as recovered_name:
            recovered_port = int(command('docker', 'port', recovered_name, '9200/tcp').rsplit(':', 1)[1])
            recovered = OpenSearch(f'http://127.0.0.1:{recovered_port}', password)
            for _ in range(120):
                try:
                    recovered.validate_recovery(first)
                    break
                except Exception:
                    time.sleep(.4)
            else:
                raise AssertionError('Restored OpenSearch did not become ready')
            for old in credentials:
                recovered.revoke(first, old)
                denied(lambda c=old: recovered.probe(first, c))
            fresh = {'credential_id': str(uuid4()), 'mode': 'read-only',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            recovered.issue(first, fresh)
            fresh_reader = recovered.scoped(fresh)
            hits = fresh_reader.request('POST', prefix + '/_search', {'query': {'match': {'title': 'energy'}}})
            assert hits['hits']['hits'][0]['_id'] == 'one'
            assert fresh_reader.request('GET', prefix + '/_mapping')[index(first)]['mappings']['properties']['kind']['type'] == 'keyword'
            assert workspace(recovered, first, fresh).request('GET', '/.kibana/_doc/fixture')['_source']['title'] == 'retained workspace'
            denied(lambda: workspace(recovered, other, fresh).request('GET', '/.kibana/_doc/fixture'))
            denied(lambda: fresh_reader.request('GET', foreign + '/_search'))
            denied(lambda: fresh_reader.request('PUT', prefix + '/_doc/forbidden', {'title': 'denied'}))
            recovered.validate_recovery(other)
        print('PASS OpenSearch stopped-volume capture and empty-volume restore: documents/mappings/IAM retained; recovered users revoked; fresh scoped reader query succeeds')
        port = int(command('docker', 'port', name, '9200/tcp').rsplit(':', 1)[1])
        endpoint = f'http://127.0.0.1:{port}'
        provider = OpenSearch(endpoint, password)
        for _ in range(120):
            try:
                provider.validate_recovery(first)
                break
            except Exception:
                time.sleep(.4)
        else:
            raise AssertionError('Original OpenSearch did not recover after capture')

        async def relay_access():
            lease = {**reader, 'resource_id': first['resource_id'], 'provider': 'opensearch',
                'expires_at': datetime.now(timezone.utc) + timedelta(seconds=.8)}
            relay = Relay(backend=lambda lease: ('127.0.0.1', port))
            relay.leases = {20000: lease}
            relay.last_success = time.monotonic()
            with patch('app.stores.relay.http_tls', return_value=None):
                server = await asyncio.start_server(lambda r, w: relay.handle(20000, r, w), '127.0.0.1', 0)
                try:
                    async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}',
                            headers={'Authorization': authorization(catalog.login(reader['credential_id']), catalog.secret_for(reader['credential_id']))}, timeout=3) as http:
                        assert (await http.get(prefix + '/_search')).status_code == 200
                        relay.leases.clear()
                        try:
                            await http.get(prefix + '/_search')
                        except httpx.TransportError:
                            pass
                        else:
                            raise AssertionError('Revoked search relay lease accepted a request')
                finally:
                    relay.leases.clear()
                    server.close()
                    await server.wait_closed()
        asyncio.run(relay_access())
        for credential in credentials:
            provider.revoke(first, credential)
            provider.revoke(first, credential)
            denied(lambda c=credential: provider.probe(first, c))
        provider.purge(first)
        provider.purge(first)
        assert not provider.console_indices(first) and provider.console_indices(other)
        provider.validate_recovery(other)
        assert workspace(provider, other, other_reader).request('GET', '/.kibana/_doc/fixture')['_source']['title'] == 'other workspace'
        print('PASS pinned OpenSearch: index-scoped readers/writers, mapping DDL, ranked/filter/facet queries, foreign/index-purge/admin/alias/settings denial, idempotent credentials/revocation, lease enforcement, measured usage and isolated purge')
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
