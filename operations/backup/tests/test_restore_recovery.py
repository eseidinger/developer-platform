import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('restore', Path(__file__).parents[1] / 'scripts/restore-recovery.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class RestoreRecoveryTests(unittest.TestCase):
    def test_restored_access_is_quarantined_before_services_start(self):
        with patch.object(restore, 'run') as run:
            restore.quarantine_hosted_access(['docker', 'compose'])
        args = run.call_args
        self.assertIn('platform', args.args[0])
        self.assertIn('ON_ERROR_STOP=1', args.args[0])
        self.assertIn(b"recovery-required", args.kwargs['data'])
        self.assertIn(b"store_control", args.kwargs['data'])
        self.assertIn(b"expires_at=LEAST(expires_at,now())", args.kwargs['data'])
        self.assertIn(b"to_regclass", args.kwargs['data'])  # Older bundles without hosted access remain supported.

    def test_latest_verified_intent_is_independent_of_selected_data_snapshot_and_checked(self):
        import hashlib
        intent = b'{"format":1,"resources":[]}'
        latest = {'id': 'b' * 64, 'time': '2026-10-17T12:00:00Z', 'paths': ['/safe/bundle']}
        older = {'id': 'a' * 64, 'time': '2026-10-16T12:00:00Z', 'paths': ['/safe/bundle']}
        manifest = {'sha256': {'store-recovery.json': hashlib.sha256(intent).hexdigest()}}
        with patch.object(restore, 'run', side_effect=[json.dumps([latest,older]).encode(), json.dumps(manifest).encode(), intent]) as run:
            self.assertEqual(restore.latest_store_intents(), intent)
        self.assertEqual(run.call_args_list[1].args[0][-2:], ['b' * 64, '/safe/bundle/manifest.json'])
        with patch.object(restore, 'run', side_effect=[json.dumps([latest]).encode(), json.dumps(manifest).encode(), b'corrupt']):
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                restore.latest_store_intents()

    def test_only_known_bootstrap_duplicates_are_accepted(self):
        restore.check_import_errors('ERROR:  role "postgres" already exists\nERROR:  database "platform" already exists\n')
        restore.check_import_errors('')
        for message in ['ERROR: permission denied', 'ERROR:  role "project_smoke" already exists',
                        'WARNING: something unexpected',
                        'ERROR:  role "postgres" already exists\nERROR:  role "postgres" already exists']:
            with self.assertRaises(RuntimeError):
                restore.check_import_errors(message)

    def test_project_secrets_are_restored_through_stdin_and_pods_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / 'project-secrets.json').write_text(json.dumps({'format': 1, 'projects': {
                'smoke': {'data': {'API_KEY': 'dmFsdWU='}, 'annotations': {'platform.example/changed-API_KEY': 't'}}}}))
            with patch.object(restore, 'run') as run:
                self.assertTrue(restore.restore_project_secrets(bundle, 'smoke'))
                self.assertFalse(restore.restore_project_secrets(bundle, 'other'))
            apply, restart = run.call_args_list
            self.assertNotIn('dmFsdWU=', ' '.join(apply.args[0]))
            body = json.loads(apply.kwargs['data'])
            self.assertEqual((body['metadata']['namespace'], body['data']), ('project-smoke', {'API_KEY': 'dmFsdWU='}))
            self.assertEqual(restart.args[0][-3:], ['rollout', 'restart', 'deployment/smoke'])
            (bundle / 'project-secrets.json').unlink()
            self.assertFalse(restore.restore_project_secrets(bundle, 'smoke'))

    def test_archive_cannot_escape_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'target'
            target.mkdir()
            archive = root / 'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as out:
                member = tarfile.TarInfo('../outside')
                member.size = 1
                out.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(tarfile.FilterError):
                restore.extract(archive, target)
            self.assertFalse((root / 'outside').exists())
