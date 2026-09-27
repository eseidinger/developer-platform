#!/usr/bin/env python3
"""Real-time stalled/overdue exercises on the existing lab; no timestamp edits."""
import argparse
import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import time
import urllib.request


def thresholds(config):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    url = config['watchdog_url']
    if not url.startswith('https://'):
        raise RuntimeError('HTTPS watchdog required')
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + config['watchdog_token']})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            data = json.load(response)
        if data.get('protocol') != 1 or data.get('max_age') != 86400 or data.get('timeout') != 7200:
            raise ValueError('Unexpected watchdog thresholds')
    except Exception:
        raise RuntimeError('Watchdog preflight failed; check configuration privately') from None
    return data


def wait_until(deadline):
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def recovered(status, before, rc, state):
    return (rc == 0 and status.get('running') is False
            and status.get('result') == 'success'
            and status.get('last_verified_capture', 0) > before['last_verified_capture']
            and status.get('last_verified_snapshot') != before['last_verified_snapshot']
            and not (state / 'notification.json').exists())


def exercise(module, config, mode, window, report, limits):
    job = module.Job(config)
    with (job.state / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = job.read('status.json', {})
        now = int(time.time())
        if (before.get('running') or before.get('result') != 'success'
                or not before.get('last_verified_snapshot')
                or not isinstance(before.get('last_verified_capture'), int)
                or not 0 <= now - before['last_verified_capture'] < limits['max_age']
                or (job.state / 'resume.json').exists()
                or (job.state / 'notification.json').exists()):
            raise RuntimeError('Require a recent successful backup without pending recovery/notification')
        evidence = dict(mode=mode, before=before, started=now, result='running',
                        email_receipt='operator confirmation required')
        module.atomic_json(report, evidence)

        def save(**fields):
            evidence.update(fields)
            module.atomic_json(report, evidence)

        def hold(deadline):
            save(stage='waiting-for-' + mode, recovery_not_before=deadline)
            print('Waiting for real ' + mode + ' threshold and notification window.', flush=True)
            wait_until(deadline)
            save(threshold_window_completed=int(time.time()))

        # Recovery is attempted after interruption or an unexpected result as well.
        success = False
        try:
            if mode == 'stalled':
                stalled = module.Job(config)
                capture = stalled.capture

                def delayed_capture(bundle):
                    status = stalled.read('status.json', {})
                    if (stalled.state / 'notification.json').exists():
                        raise RuntimeError('Backup start signal not delivered')
                    if any(status.get(k) != before[k] for k in
                           ['last_verified_capture', 'last_verified_snapshot']):
                        raise RuntimeError('Previous verified capture changed unexpectedly')
                    save(stalled_attempt=status)
                    hold(status['started'] + limits['timeout'] + 1 + window)
                    save(stage='recovering')
                    capture(bundle)

                stalled.capture = delayed_capture
                rc = stalled.run()
                status = job.read('status.json', {})
                success = recovered(status, before, rc, job.state)
                save(recovery=status, recovery_exit_code=rc)
                if not success:
                    raise RuntimeError('Stalled attempt did not finish as a verified backup')
            else:
                # No start/completion event is fabricated: previous capture ages naturally.
                hold(before['last_verified_capture'] + limits['max_age'] + 1 + window)
        except BaseException:
            save(result='interrupted-or-failed')
            raise
        finally:
            if not success:
                save(stage='recovering')
                time.sleep(2)
                rc = job.run()
                status = job.read('status.json', {})
                success = recovered(status, before, rc, job.state)
                save(recovery=status, recovery_exit_code=rc)
                if not success:
                    save(result='recovery-failed', stage='needs-attention')
                    raise RuntimeError('Recovery not verified; inspect backup status and journal')
        save(result='passed', stage='complete', finished=int(time.time()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['stalled', 'overdue'], required=True)
    parser.add_argument('--window', type=int, default=300)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not 60 <= args.window <= 1800:
        parser.error('window must be 60–1800 seconds')
    os.umask(0o077)
    loader = importlib.machinery.SourceFileLoader('installed_backup', '/usr/local/sbin/platform-backup')
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    config = json.loads(Path('/etc/developer-platform/backup/job.json').read_text())

    def interrupted(*_):
        raise RuntimeError('Interrupted; attempting recovery')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        limits = thresholds(config)
        exercise(module, config, args.mode, args.window, args.report, limits)
    except BaseException:
        # Keep preflight errors inspectable without leaking configuration values.
        if not args.report.exists():
            module.atomic_json(args.report, dict(result='preflight-failed', mode=args.mode))
        else:
            evidence = json.loads(args.report.read_text())
            if evidence.get('result') == 'running':
                evidence['result'] = 'failed'
                module.atomic_json(args.report, evidence)
        raise


if __name__ == '__main__':
    main()
