import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'failure_drill', Path(__file__).parents[1] / 'scripts/drill-backup-failure.py')
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


class FailureDrillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.calls = []
        self.pending = False
        self.recovery_fails = False
        owner = self

        def write(path, data):
            path.write_text(json.dumps(data))

        class Job:
            def __init__(self, config):
                self.state = owner.state
                self.config = config

            def read(self, name, default):
                p = self.state / name
                return json.loads(p.read_text()) if p.exists() else default

            def run(self):
                failed = self.config.get('docker') == '/usr/bin/false'
                owner.calls.append('failure' if failed else 'recovery')
                status = self.read('status.json', {})
                status.update(run_id='failure' if failed else 'recovery', running=False)
                if failed or owner.recovery_fails:
                    status.update(result='failure', stage='database capture')
                else:
                    status.update(result='success', stage='complete',
                                  last_verified_capture=200, last_verified_snapshot='new')
                write(self.state / 'status.json', status)
                notification = self.state / 'notification.json'
                if failed and owner.pending:
                    write(notification, {'event': 'failure'})
                elif notification.exists():
                    notification.unlink()
                return 1 if failed or owner.recovery_fails else 0

        self.module = types.SimpleNamespace(Job=Job, atomic_json=write)
        self.report = self.state / 'report.json'
        write(self.state / 'status.json', dict(result='success', running=False,
              run_id='old', last_verified_capture=100, last_verified_snapshot='old'))

    def test_failure_preserves_previous_capture_then_recovers(self):
        with patch.object(drill.time, 'sleep') as sleep:
            drill.exercise(self.module, {}, 300, self.report)
        evidence = json.loads(self.report.read_text())
        self.assertEqual(self.calls, ['failure', 'recovery'])
        self.assertEqual(evidence['failure']['last_verified_snapshot'], 'old')
        self.assertEqual(evidence['recovery']['last_verified_snapshot'], 'new')
        self.assertEqual(evidence['result'], 'passed')
        sleep.assert_any_call(300)

    def test_interruption_during_wait_still_recovers(self):
        with patch.object(drill.time, 'sleep', side_effect=[RuntimeError('interrupted'), None]):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                drill.exercise(self.module, {}, 300, self.report)
        self.assertEqual(self.calls, ['failure', 'recovery'])
        self.assertNotIn('result', json.loads(self.report.read_text()))

    def test_failed_signal_delivery_recovers_without_notification_wait(self):
        self.pending = True
        with patch.object(drill.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'delivery is pending'):
                drill.exercise(self.module, {}, 300, self.report)
        self.assertEqual(self.calls, ['failure', 'recovery'])
        sleep.assert_called_once_with(2)

    def test_recovery_failure_does_not_pass(self):
        self.recovery_fails = True
        with patch.object(drill.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Recovery not fully verified'):
                drill.exercise(self.module, {}, 300, self.report)
        self.assertNotIn('result', json.loads(self.report.read_text()))

    def test_existing_pending_work_refuses_injection(self):
        (self.state / 'resume.json').write_text('[]')
        with self.assertRaisesRegex(RuntimeError, 'prior backup'):
            drill.exercise(self.module, {}, 300, self.report)
        self.assertEqual(self.calls, [])

    def test_existing_lock_refuses_injection(self):
        with (self.state / 'lock').open('a') as lock:
            drill.fcntl.flock(lock, drill.fcntl.LOCK_EX | drill.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                drill.exercise(self.module, {}, 300, self.report)
        self.assertEqual(self.calls, [])
