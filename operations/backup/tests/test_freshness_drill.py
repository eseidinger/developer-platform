import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'freshness_drill', Path(__file__).parents[1] / 'scripts/drill-backup-freshness.py')
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


class FreshnessDrillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.clock = 100000
        self.starts = []
        self.capture_times = []
        self.waits = []
        self.recovery_fails = False
        owner = self

        def write(path, data):
            path.write_text(json.dumps(data))

        class Job:
            def __init__(self, config):
                self.state = owner.state

            def read(self, name, default):
                p = self.state / name
                return json.loads(p.read_text()) if p.exists() else default

            def capture(self, bundle):
                owner.capture_times.append(owner.clock)
                if owner.recovery_fails:
                    raise RuntimeError('capture failure')

            def run(self):
                started = int(owner.clock)
                owner.starts.append(started)
                status = self.read('status.json', {})
                status.update(started=started, running=True, run_id=str(started))
                write(self.state / 'status.json', status)
                try:
                    self.capture(None)
                    status.update(result='success', running=False,
                                  last_verified_capture=started,
                                  last_verified_snapshot='snapshot-' + str(started))
                    rc = 0
                except Exception:
                    status.update(result='failure', running=False)
                    rc = 1
                write(self.state / 'status.json', status)
                return rc

        self.module = types.SimpleNamespace(Job=Job, atomic_json=write)
        self.report = self.state / 'report.json'
        self.before = dict(result='success', running=False, run_id='old',
                           last_verified_capture=99000, last_verified_snapshot='old')
        write(self.state / 'status.json', self.before)
        self.limits = dict(max_age=86400, timeout=7200)
        self.time_patch = patch.object(drill.time, 'time', side_effect=lambda: self.clock)
        self.sleep_patch = patch.object(drill.time, 'sleep', side_effect=self.advance)
        self.time_patch.start()
        self.sleep_patch.start()
        self.addCleanup(self.time_patch.stop)
        self.addCleanup(self.sleep_patch.stop)

    def advance(self, seconds):
        self.clock += seconds

    def wait(self, deadline):
        self.waits.append(deadline)
        status = json.loads((self.state / 'status.json').read_text())
        self.assertEqual(status['last_verified_capture'], 99000)
        self.assertEqual(status['last_verified_snapshot'], 'old')
        self.clock = deadline

    def run_drill(self, mode):
        with patch.object(drill, 'wait_until', side_effect=self.wait):
            drill.exercise(self.module, {}, mode, 300, self.report, self.limits)
        return json.loads(self.report.read_text())

    def test_stalled_waits_from_real_start_and_then_captures(self):
        evidence = self.run_drill('stalled')
        self.assertEqual(self.waits, [100000 + 7200 + 1 + 300])
        self.assertEqual(self.starts, [100000])
        self.assertEqual(self.capture_times, self.waits)
        self.assertEqual(evidence['result'], 'passed')

    def test_overdue_ages_existing_capture_without_a_start_event(self):
        def wait(deadline):
            self.assertEqual(self.starts, [])
            self.wait(deadline)
        with patch.object(drill, 'wait_until', side_effect=wait):
            drill.exercise(self.module, {}, 'overdue', 300, self.report, self.limits)
        self.assertEqual(self.waits, [99000 + 86400 + 1 + 300])
        self.assertEqual(len(self.starts), 1)
        self.assertGreater(self.starts[0], self.waits[0])
        self.assertEqual(json.loads(self.report.read_text())['result'], 'passed')

    def test_interruption_attempts_recovery_and_does_not_pass(self):
        with patch.object(drill, 'wait_until', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                drill.exercise(self.module, {}, 'overdue', 300, self.report, self.limits)
        evidence = json.loads(self.report.read_text())
        self.assertEqual(len(self.starts), 1)
        self.assertEqual(evidence['recovery']['result'], 'success')
        self.assertEqual(evidence['result'], 'interrupted-or-failed')

    def test_stalled_interruption_runs_a_fresh_recovery_attempt(self):
        with patch.object(drill, 'wait_until', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'Stalled attempt'):
                drill.exercise(self.module, {}, 'stalled', 300, self.report, self.limits)
        self.assertEqual(len(self.starts), 2)
        self.assertEqual(json.loads(self.report.read_text())['recovery']['result'], 'success')

    def test_recovery_failure_is_explicit(self):
        self.recovery_fails = True
        with self.assertRaisesRegex(RuntimeError, 'Recovery not verified'):
            self.run_drill('overdue')
        self.assertEqual(json.loads(self.report.read_text())['result'], 'recovery-failed')

    def test_pending_work_refuses_drill(self):
        (self.state / 'notification.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'recent successful backup'):
            self.run_drill('stalled')
        self.assertEqual(self.starts, [])
        self.assertEqual(self.waits, [])

    def test_existing_lock_refuses_drill(self):
        with (self.state / 'lock').open('a') as lock:
            drill.fcntl.flock(lock, drill.fcntl.LOCK_EX | drill.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_drill('overdue')
        self.assertEqual(self.starts, [])

    def test_already_overdue_capture_is_not_a_healthy_baseline(self):
        self.clock = 99000 + 86401
        with self.assertRaisesRegex(RuntimeError, 'recent successful backup'):
            self.run_drill('overdue')

    def test_wait_until_uses_bounded_sleeps_and_real_deadline(self):
        drill.wait_until(self.clock + 65)
        self.assertEqual(self.clock, 100065)
