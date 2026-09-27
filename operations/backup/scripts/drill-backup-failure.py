#!/usr/bin/env python3
"""Exercise failure/recovery on the existing lab using the installed backup runner."""
import argparse
import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import time


def exercise(module, config, wait_seconds, report):
    normal = module.Job(config)
    with (normal.state / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = normal.read('status.json', {})
        if (before.get('running') or before.get('result') != 'success'
                or not before.get('last_verified_snapshot')
                or (normal.state / 'resume.json').exists()
                or (normal.state / 'notification.json').exists()):
            raise RuntimeError('Require a successful prior backup with no recovery or notification pending')
        evidence = {'before': before, 'email_receipt': 'operator confirmation required'}
        module.atomic_json(report, evidence)
        failed = module.Job(dict(config, docker='/usr/bin/false'))
        try:
            rc = failed.run()
            status = normal.read('status.json', {})
            evidence['failure'] = status
            module.atomic_json(report, evidence)
            if (rc != 1 or status.get('result') != 'failure'
                    or status.get('stage') != 'database capture'
                    or status.get('running') is not False
                    or status.get('run_id') == before.get('run_id')
                    or any(status.get(k) != before.get(k) for k in
                           ['last_verified_capture', 'last_verified_snapshot'])):
                raise RuntimeError('Expected capture failure preserving prior verified backup')
            if (normal.state / 'notification.json').exists():
                raise RuntimeError('Failure signal delivery is pending; restoring normal backup now')
            print('Failure recorded and watchdog signal accepted; waiting for notification window.', flush=True)
            time.sleep(wait_seconds)
        finally:
            # Guarantee a distinct second even when injection fails immediately.
            time.sleep(2)
            print('Running normal verified recovery backup.', flush=True)
            rc = normal.run()
            recovered = normal.read('status.json', {})
            evidence['recovery'] = recovered
            evidence['recovery_exit_code'] = rc
            module.atomic_json(report, evidence)
            if (rc != 0 or recovered.get('result') != 'success'
                    or recovered.get('running') is not False
                    or recovered.get('last_verified_capture', 0) <= before.get('last_verified_capture', 0)
                    or recovered.get('last_verified_snapshot') == before.get('last_verified_snapshot')
                    or (normal.state / 'notification.json').exists()):
                raise RuntimeError('Recovery not fully verified; inspect backup status and notifications')
        evidence['result'] = 'passed'
        module.atomic_json(report, evidence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-seconds', type=int, default=300)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not 60 <= args.wait_seconds <= 1800:
        parser.error('wait-seconds must be between 60 and 1800')
    os.umask(0o077)
    loader = importlib.machinery.SourceFileLoader('installed_backup', '/usr/local/sbin/platform-backup')
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    config = json.loads(Path('/etc/developer-platform/backup/job.json').read_text())

    def interrupted(signum, frame):
        raise RuntimeError('Drill interrupted; attempting normal backup recovery')
    signal.signal(signal.SIGTERM, interrupted)
    exercise(module, config, args.wait_seconds, args.report)


if __name__ == '__main__':
    main()
