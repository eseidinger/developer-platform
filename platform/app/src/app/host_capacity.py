"""Resource-only host snapshot; the API never receives the Docker socket."""
import json
import logging
import math
import os
from pathlib import Path
import re
import tempfile
import time

import httpx

SNAPSHOT = Path('/run/capacity/host.json')
MAX_AGE_SECONDS = 60
NATIVE_LABEL = 'developer-platform.neo4j-resource'


def positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('Invalid host allocation')
    return value


def collect(engine):
    info = engine('GET', '/info')
    cpu = positive(info['NCPU']) * 1000
    memory = positive(info['MemTotal']) // 1048576
    nodes, services = {}, []
    for summary in engine('GET', '/containers/json?all=true'):
        labels = summary.get('Labels') or {}
        name = (summary.get('Names') or [''])[0].lstrip('/')
        node = re.fullmatch(r'k3d-workloads-(?:server|agent)-[0-9]+', name)
        managed = labels.get('com.docker.compose.project') == 'developer-platform'
        native = NATIVE_LABEL in labels
        running = summary.get('State') in {'running', 'restarting', 'paused'}
        if name == 'k3d-workloads-serverlb':
            continue  # Included in the explicit host process allowance.
        if not (node or managed or native or running):
            continue
        container = engine('GET', '/containers/' + summary['Id'] + '/json')
        limits = container['HostConfig']
        # Completed one-shot initializers are covered by the host allowance.
        if managed and labels.get('com.docker.compose.service') in {'keycloak-db-init', 'keycloak-realm-init', 'opensearch-init'}:
            continue
        memory_bytes = positive(limits['Memory'])
        quota = limits.get('NanoCpus', 0)
        if not isinstance(quota, int) or isinstance(quota, bool) or quota < 0:
            raise ValueError('Invalid container CPU allocation')
        if not quota and limits.get('CpuQuota', 0) > 0:
            quota = math.ceil(limits['CpuQuota'] * 1_000_000_000 / positive(limits['CpuPeriod']))
        allocation = {'cpu_millicores': math.ceil(quota / 1_000_000),
                      'memory_mib': memory_bytes // 1048576 if node else math.ceil(memory_bytes / 1048576)}
        if node:
            nodes[name] = {**allocation, 'cpu_millicores': min(cpu, allocation['cpu_millicores'] or cpu)}
        else:
            services.append({'name': name, **allocation,
                             'cpu_unbounded': not quota})
    if not nodes:
        raise ValueError('Workload nodes unavailable')
    return {'format': 1, 'state': 'ok', 'captured_at': time.time(),
            'capacity': {'cpu_millicores': cpu, 'memory_mib': memory},
            'nodes': nodes, 'services': services}


def read_snapshot(path=None, now=None):
    """Fail closed on missing, stale, partial or invalid resource data."""
    try:
        path = Path(path or os.environ.get('CAPACITY_HOST_SNAPSHOT', SNAPSHOT))
        if path.stat().st_size > 1048576:
            raise ValueError
        data = json.loads(path.read_text())
        if data.get('state') != 'ok':
            return {'state': 'unavailable', 'reason': 'HostCapacityCollectionFailed'}
        if data.get('format') != 1:
            raise ValueError
        timestamp = data['captured_at']
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            raise ValueError
        age = (time.time() if now is None else now) - timestamp
        if age < -5 or age > MAX_AGE_SECONDS:
            return {'state': 'unavailable', 'reason': 'HostCapacitySnapshotStale'}
        for value in data['capacity'].values():
            positive(value)
        if set(data['capacity']) != {'cpu_millicores', 'memory_mib'} or not data['nodes']:
            raise ValueError
        for value in data['nodes'].values():
            positive(value['cpu_millicores']); positive(value['memory_mib'])
        if not isinstance(data['services'], list):
            raise ValueError
        for value in data['services']:
            positive(value['memory_mib'])
            if type(value['cpu_millicores']) is not int or value['cpu_millicores'] < 0 or type(value['cpu_unbounded']) is not bool:
                raise ValueError
            if not isinstance(value['name'], str):
                raise ValueError
        return data
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {'state': 'unavailable', 'reason': 'HostCapacitySnapshotUnavailable'}


def write_snapshot(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(data, output, allow_nan=False)
            output.flush()
            os.fchmod(output.fileno(), 0o644)  # Resource allocations only, no credentials.
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    path = Path(os.environ.get('CAPACITY_HOST_SNAPSHOT', '/var/lib/platform-capacity/host.json'))
    with httpx.Client(transport=httpx.HTTPTransport(uds='/var/run/docker.sock'),
                      base_url='http://docker', timeout=5, trust_env=False) as client:
        def engine(method, endpoint):
            response = client.request(method, '/v1.47' + endpoint)
            response.raise_for_status()
            return response.json()
        while True:
            try:
                data = collect(engine)
            except Exception as error:
                logging.error('Host capacity collection failed error_type=%s', type(error).__name__)
                data = {'format': 1, 'state': 'unavailable', 'captured_at': time.time()}
            write_snapshot(path, data)
            time.sleep(15)


if __name__ == '__main__':
    main()
