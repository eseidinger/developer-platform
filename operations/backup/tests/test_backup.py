import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup_platform', Path(__file__).parents[1] / 'scripts/backup-platform.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.job = backup.Job({'platform_dir': str(self.root), 'state_dir': str(self.root / 'state'),
                               'instance': 'test-installation', 'watchdog_url': 'https://example.invalid/backup.php',
                               'watchdog_token': 'test-only'})

    def test_failed_upload_keeps_previous_success_and_skips_retention(self):
        backup.atomic_json(self.job.state / 'status.json', {'last_verified_capture': 123, 'last_verified_snapshot': 'old'})
        with patch.object(self.job, 'capture', side_effect=lambda p: (p / 'data').write_text('data')), \
             patch.object(self.job, 'notify'), \
             patch.object(self.job, 'command', side_effect=backup.BackupError('upload')), \
             patch.object(self.job, 'retention') as retention:
            self.assertEqual(self.job.run(), 1)
            retention.assert_not_called()
        status = self.job.read('status.json', {})
        self.assertEqual(status['last_verified_capture'], 123)
        self.assertEqual(status['last_verified_snapshot'], 'old')
        self.assertEqual(status['result'], 'failure')
        self.assertFalse((self.job.state / 'work').exists())

    def test_purge_intents_are_captured_privately_and_acknowledgment_is_version_pinned(self):
        bundle = self.root / 'bundle'; bundle.mkdir()
        manifest = {'format': 1, 'captured_at': '2026-10-17T00:00:00Z', 'resources': [
            {'resource_id': '11111111-1111-1111-1111-111111111111', 'state': 'purging', 'version': 3}]}
        with patch.object(self.job, 'compose', side_effect=[b't', json.dumps(manifest).encode()]):
            self.job.store_recovery_manifest(bundle)
        self.assertEqual((bundle / 'store-recovery.json').stat().st_mode & 0o777, 0o600)
        with patch.object(self.job, 'compose') as compose:
            self.job.acknowledge_store_purges(bundle, 'a' * 64)
        sql = compose.call_args.args[-1]
        self.assertIn("r.state='purging'", sql)
        self.assertIn("r.version=(c.item->>'version')::bigint", sql)
        self.assertNotIn('11111111-1111', sql)  # JSON travels as hex, not interpolated literals.

    def test_upload_failure_cannot_acknowledge_purge_intent(self):
        with patch.object(self.job, 'capture', side_effect=lambda p: (p / 'data').write_text('data')), \
                patch.object(self.job, 'notify'), patch.object(self.job, 'command', side_effect=backup.BackupError()), \
                patch.object(self.job, 'acknowledge_store_purges') as acknowledge:
            self.assertEqual(self.job.run(), 1)
        acknowledge.assert_not_called()

    def test_capture_failure_restarts_both_services(self):
        bundle = self.root / 'bundle'; bundle.mkdir()
        volumes = {}
        for name in ['data', 'config', 'grafana']:
            volumes[name] = self.root / name; volumes[name].mkdir()
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            if args[1] == 'inspect':
                targets = ['/data', '/config'] if args[2] == 'proxy' else ['/var/lib/grafana']
                return json.dumps([{'State': {'Running': True}, 'Mounts': [
                    {'Destination': t, 'Type': 'volume', 'Source': str(volumes[t.rsplit('/', 1)[-1]])} for t in targets]}]).encode()
            return b''
        with patch.object(self.job, 'compose', side_effect=lambda *a: a[-1].encode()), \
             patch.object(self.job, 'command', side_effect=command), \
             patch.object(backup.tarfile, 'open', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.job.service_state(bundle)
        self.assertIn([self.job.docker, 'start', 'proxy'], calls)
        self.assertIn([self.job.docker, 'start', 'grafana'], calls)
        self.assertFalse((self.job.state / 'resume.json').exists())

    def test_retained_shared_store_volumes_are_required_and_unknown_providers_fail_closed(self):
        bundle = self.root / 'bundle'; bundle.mkdir()
        path = bundle / 'store-recovery.json'
        backup.atomic_json(path, {'resources': [
            {'provider': provider, 'state': state} for provider, state in
            [('postgresql', 'active'), ('s3', 'retired'), ('qdrant', 'active'), ('opensearch', 'purging'), ('neo4j', 'purged')]]})
        with patch.object(self.job, 'volume_state') as volumes:
            self.job.data_store_state(bundle)
        self.assertEqual(volumes.call_args.args[1], [('opensearch', ['/usr/share/opensearch/data']),
            ('qdrant', ['/qdrant/storage']), ('rustfs', ['/data'])])
        backup.atomic_json(path, {'resources': [{'provider': 'neo4j', 'state': 'active'}]})
        with patch.object(self.job, 'volume_state') as volumes, self.assertRaises(backup.BackupError):
            self.job.data_store_state(bundle)
        volumes.assert_not_called()

    def test_shared_data_capture_and_sql_dump_share_the_pause_and_lifecycle_lock(self):
        events = []
        @contextmanager
        def fenced():
            events.append('paused')
            try:
                yield
            finally:
                events.append('resumed')
        def dump(bundle):
            self.assertEqual(events, ['paused', 'intents', 'stopped-volume-capture'])
            events.append('sql')
        with patch.object(self.job, 'catalog_snapshot', side_effect=fenced), \
                patch.object(self.job, 'check_graph_sources'), \
                patch.object(self.job, 'store_recovery_manifest', side_effect=lambda bundle: events.append('intents')), \
                patch.object(self.job, 'data_store_state', side_effect=lambda bundle: events.append('stopped-volume-capture')), \
                patch.object(self.job, 'dump', side_effect=dump), \
                patch.object(self.job, 'project_secrets', side_effect=RuntimeError('stop fixture before host config capture')):
            with self.assertRaises(RuntimeError):
                self.job.capture(self.root)
        self.assertEqual(events, ['paused', 'intents', 'stopped-volume-capture', 'sql', 'resumed'])

    def kubectl_listing(self, items):
        (self.root / '.runtime').mkdir(exist_ok=True)
        (self.root / '.runtime/admin.kubeconfig').write_text('x')
        return patch.object(self.job, 'command', return_value=json.dumps({'items': items}).encode())

    def test_project_secrets_are_captured_privately_for_project_namespaces_only(self):
        bundle = self.root / 'bundle'; bundle.mkdir()
        items = [
            {'metadata': {'namespace': 'project-smoke', 'annotations': {
                'platform.example/changed-API_KEY': 't', 'other': 'x'}}, 'data': {'API_KEY': 'dmFsdWU='}},
            {'metadata': {'namespace': 'platform-system'}, 'data': {'A': 'Yg=='}},
            {'metadata': {'namespace': 'project-empty'}, 'data': {}}]
        with self.kubectl_listing(items) as command:
            self.job.project_secrets(bundle)
        argv = command.call_args.args[0]
        self.assertIn('metadata.name=app-secrets', argv)
        stored = json.loads((bundle / 'project-secrets.json').read_text())
        self.assertEqual(stored['projects'], {'smoke': {
            'data': {'API_KEY': 'dmFsdWU='}, 'annotations': {'platform.example/changed-API_KEY': 't'}}})
        self.assertEqual((bundle / 'project-secrets.json').stat().st_mode & 0o777, 0o600)

    def test_secret_capture_fails_closed(self):
        bundle = self.root / 'bundle'; bundle.mkdir()
        with self.assertRaises(backup.BackupError):
            self.job.project_secrets(bundle)
        with self.kubectl_listing([]), patch.object(self.job, 'command', side_effect=backup.BackupError('x')):
            with self.assertRaises(backup.BackupError):
                self.job.project_secrets(bundle)
        self.assertFalse((bundle / 'project-secrets.json').exists())

    def test_resume_attempts_all_services_and_preserves_intent_on_failure(self):
        backup.atomic_json(self.job.state / 'resume.json', ['proxy', 'grafana'])
        with patch.object(self.job, 'command', side_effect=[backup.BackupError('failed'), b'']) as command:
            with self.assertRaises(backup.BackupError): self.job.resume()
            self.assertEqual(command.call_count, 2)
        self.assertTrue((self.job.state / 'resume.json').exists())

    def test_recovery_after_forced_termination_marks_failure_and_retains_outbox(self):
        backup.atomic_json(self.job.state / 'resume.json', ['proxy'])
        backup.atomic_json(self.job.state / 'status.json', {'run_id': 'a' * 32, 'started': 123, 'running': True,
                                                         'last_verified_capture': 100})
        (self.job.state / 'work').mkdir()
        with patch.object(self.job, 'command', return_value=b''), patch.object(self.job, 'notify', side_effect=OSError()):
            self.job.recover()
        self.assertEqual(self.job.read('notification.json', {})['event'], 'failure')
        self.assertEqual(self.job.read('status.json', {})['last_verified_capture'], 100)
        self.assertFalse((self.job.state / 'work').exists())
        with patch.object(self.job, 'notify'):
            self.assertTrue(self.job.retry_notification())
        self.assertFalse((self.job.state / 'notification.json').exists())

    def test_readback_corruption_is_rejected(self):
        bundle = self.root / 'bundle'; bundle.mkdir()
        backup.atomic_json(bundle / 'manifest.json', {'sha256': {'data': '0' * 64}})
        target = self.root / 'readback' / 'bundle'; target.mkdir(parents=True)
        (target / 'manifest.json').write_bytes((bundle / 'manifest.json').read_bytes())
        (target / 'data').write_text('corrupted')
        with patch.object(self.job, 'command', return_value=b''):
            with self.assertRaises(backup.BackupError): self.job.verify('snapshot', bundle, self.root)

    def test_retention_scoped_to_verified_installation(self):
        with patch.object(self.job, 'command') as command:
            self.job.retention()
        argv = command.call_args_list[0].args[0]
        self.assertEqual(argv[argv.index('--host') + 1], 'test-installation')
        self.assertEqual(argv[argv.index('--tag') + 1], 'developer-platform,verified')
        for flag, value in [('--keep-daily', '14'), ('--keep-weekly', '8'), ('--keep-monthly', '6')]:
            self.assertEqual(argv[argv.index(flag) + 1], value)

    @unittest.skipUnless(os.environ.get('RESTIC_TEST_BINARY'), 'Set RESTIC_TEST_BINARY for local encrypted-repository test')
    def test_real_restic_roundtrip_retention_and_notification_failure(self):
        binary = os.environ['RESTIC_TEST_BINARY']
        self.job.restic = binary
        environment = {'RESTIC_REPOSITORY': str(self.root / 'repository'), 'RESTIC_PASSWORD': 'local-test-password',
                       'RESTIC_CACHE_DIR': str(self.root / 'cache')}
        with patch.dict(os.environ, environment):
            subprocess.run([binary, 'init'], check=True, stdout=subprocess.DEVNULL)
            pending = self.root / 'unverified-data'; pending.write_text('pending marker')
            subprocess.run([binary, 'backup', '--host', 'test-installation', '--tag', 'developer-platform',
                            '--tag', 'pending', str(pending)], check=True, stdout=subprocess.DEVNULL)
            with patch.object(self.job, 'capture', side_effect=lambda p: (p / 'data').write_text('recovery marker')), \
                 patch.object(self.job, 'notify', side_effect=OSError('mail path unavailable')):
                self.assertEqual(self.job.run(), 1)  # Valid backup, pending delivery; not false storage failure.
            status = self.job.read('status.json', {})
            self.assertEqual(status['result'], 'success')
            self.assertEqual(self.job.read('notification.json', {})['event'], 'success')
            snapshots = json.loads(subprocess.check_output([binary, 'snapshots', '--json']))
            self.assertEqual(len(snapshots), 2)
            verified = [item for item in snapshots if 'verified' in item.get('tags', [])]
            self.assertEqual(len(verified), 1)
            self.assertEqual(status['last_verified_snapshot'], verified[0]['id'])
            self.assertNotIn('pending', verified[0]['tags'])
            self.assertEqual(len([item for item in snapshots if 'pending' in item.get('tags', [])]), 1)


if __name__ == '__main__':
    unittest.main()
