import importlib.util
import hashlib
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('checks', Path(__file__).parents[1] / 'scripts/test-recovery.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class RecoveryChecks(unittest.TestCase):
    def test_bundle_detects_corruption_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'data').write_bytes(b'original')
            manifest = {'format': 1, 'sha256': {'data': hashlib.sha256(b'original').hexdigest()}}
            (p / 'manifest.json').write_text(json.dumps(manifest))
            checks.verify_bundle(p)
            (p / 'data').write_bytes(b'corrupt')
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                checks.verify_bundle(p)
            manifest['sha256'] = {'../outside': 'bad'}
            (p / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                checks.verify_bundle(p)

    def test_marker_rejects_sql_injection(self):
        with self.assertRaisesRegex(RuntimeError, 'Invalid marker'):
            checks.marker_sql({'table': 'x; DROP TABLE projects', 'value': 'a' * 32})

    def test_seed_records_only_committed_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def validate_command(args, cwd, code):
                compile(code, '<marker>', 'exec')
            with patch.object(checks, 'command', side_effect=validate_command):
                checks.seed(root, 'smoke', root / 'receipt.json')
            self.assertTrue(json.loads((root / 'receipt.json').read_text())['seeded'])
            with patch.object(checks, 'command', side_effect=RuntimeError('db failure')):
                with self.assertRaises(RuntimeError):
                    checks.seed(root, 'smoke', root / 'failed.json')
            self.assertFalse(json.loads((root / 'failed.json').read_text())['seeded'])

    def test_failed_pod_is_retained_without_dumping_credentials(self):
        calls = []
        def command(args, root, data=None, timeout=30):
            calls.append(args)
            if 'get' in args:
                return json.dumps({'status': {'phase': 'Pending', 'containerStatuses': [
                    {'state': {'waiting': {'reason': 'ImagePullBackOff'}}}]}})
            return ''
        with patch.object(checks, 'command', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'ImagePullBackOff'):
                checks.check_pod(Path('/tmp'), 'smoke', 'postgres:test', None)
        self.assertFalse(any('delete' in c for c in calls))

    def test_monitoring_waits_for_first_successful_scrape(self):
        states = [[], [{'health': 'unknown'}], [{'health': 'down'}], [{'health': 'up'}]]
        replies = [json.dumps({'data': {'activeTargets': targets}}).encode() for targets in states]
        with patch.object(checks, 'request', side_effect=replies) as request, \
             patch.object(checks.time, 'sleep'):
            checks.retry(checks.check_targets, seconds=180)
        self.assertEqual(request.call_count, 4)

    def test_unhealthy_monitoring_fails_at_deadline(self):
        with patch.object(checks, 'request', return_value=b'{"database":"failed"}'), \
             patch.object(checks.time, 'monotonic', side_effect=[0, 181]):
            with self.assertRaisesRegex(RuntimeError, 'Grafana'):
                checks.retry(checks.check_grafana, seconds=180)

    def test_sql_delimiters_survive_kubelet_and_shell(self):
        marker = {'table': 'recovery_marker_' + 'a' * 32, 'value': 'b' * 32}
        for receipt in [None, marker]:
            with self.subTest(marker=receipt is not None):
                pod = checks.test_pod('smoke', 'postgres:test', receipt)
                argument = pod['spec']['containers'][0]['args'][0]
                # Emulate kubelet's documented escaping, then execute the actual shell heredoc.
                expanded = argument.replace('$$', '$')
                shell = 'sleep() { :; }; psql() { cat; };\n' + expanded
                result = subprocess.run(['/bin/sh', '-ec', shell], capture_output=True, text=True, check=True)
                self.assertIn('DO $$ BEGIN', result.stdout)
                self.assertIn('END $$;', result.stdout)
                self.assertNotIn('DO $ BEGIN', result.stdout)
                self.assertEqual(result.stdout.count('DO $$ BEGIN'), 2 if receipt else 1)
