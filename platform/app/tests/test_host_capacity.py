import json
from pathlib import Path
import tempfile
import unittest

from app.host_capacity import collect, read_snapshot, write_snapshot


class HostCapacityTests(unittest.TestCase):
    def engine(self, memory=512*1048576):
        summaries = [
            {'Id': 'node', 'Names': ['/k3d-workloads-agent-0'], 'State': 'running', 'Labels': {}},
            {'Id': 'shared', 'Names': ['/shared'], 'State': 'running', 'Labels': {'com.docker.compose.project': 'developer-platform'}},
            {'Id': 'retained', 'Names': ['/native-retained'], 'State': 'exited', 'Labels': {'developer-platform.neo4j-resource': 'synthetic'}},
            {'Id': 'init', 'Names': ['/init'], 'State': 'exited', 'Labels': {
                'com.docker.compose.project': 'developer-platform', 'com.docker.compose.service': 'keycloak-db-init'}},
        ]
        containers = {name: {'HostConfig': {'Memory': allocation, 'NanoCpus': cpu,
                                            'RestartPolicy': {'Name': restart}},
                              'Config': {'Env': ['PRIVATE_SECRET=MUST_NOT_APPEAR']}}
                      for name, allocation, cpu, restart in [
                          ('node', 4*1073741824, 0, 'unless-stopped'),
                          ('shared', memory, 0, 'unless-stopped'),
                          ('retained', 1610612736, 1000000000, 'unless-stopped'),
                          ('init', 0, 0, 'no')]}
        def request(method, endpoint):
            self.assertEqual(method, 'GET')
            if endpoint == '/info': return {'NCPU': 16, 'MemTotal': 32*1073741824}
            if endpoint == '/containers/json?all=true': return summaries
            return containers[endpoint.split('/')[2]]
        return request

    def test_projection_omits_credentials_counts_retained_instances_and_excludes_initializers(self):
        result = collect(self.engine())
        self.assertEqual(result['capacity'], {'cpu_millicores': 16000, 'memory_mib': 32768})
        self.assertEqual(result['nodes'], {'k3d-workloads-agent-0': {'cpu_millicores': 16000, 'memory_mib': 4096}})
        self.assertEqual([s['name'] for s in result['services']], ['shared', 'native-retained'])
        self.assertEqual(sum(s['memory_mib'] for s in result['services']), 2048)
        self.assertTrue(result['services'][0]['cpu_unbounded'])
        self.assertNotIn('MUST_NOT_APPEAR', json.dumps(result))

    def test_unbounded_memory_never_becomes_zero_cost_capacity(self):
        with self.assertRaises(ValueError):
            collect(self.engine(memory=0))

    def test_service_budget_rounds_up_fractional_mib(self):
        self.assertEqual(collect(self.engine(memory=1048577))['services'][0]['memory_mib'], 2)

    def test_snapshot_expiry_and_failed_refresh_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'host.json'
            self.assertEqual(read_snapshot(path)['state'], 'unavailable')
            data = {**collect(self.engine()), 'captured_at': 100}
            write_snapshot(path, data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(read_snapshot(path, now=110)['state'], 'ok')
            self.assertEqual(read_snapshot(path, now=161)['reason'], 'HostCapacitySnapshotStale')
            self.assertEqual(read_snapshot(path, now=90)['reason'], 'HostCapacitySnapshotStale')
            write_snapshot(path, {'state': 'unavailable'})
            self.assertEqual(read_snapshot(path)['reason'], 'HostCapacityCollectionFailed')


if __name__ == '__main__':
    unittest.main()
