#!/usr/bin/env python3
"""Disposable local PHP/MySQL test. Email handoff uses /bin/true, never sends mail."""
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
env = dict(os.environ, TEST_PASSWORD=secrets.token_hex(24), TEST_TOKEN=secrets.token_hex(32), TEST_BACKUP_TOKEN=secrets.token_hex(32))
compose = ["docker", "compose", "-p", "platform-watchdog-test", "-f", "tests/compose.watchdog.yaml"]
def run(*args, **kwargs):
    return subprocess.run(compose + list(args), env=env, check=True, **kwargs)
existing = run("ps", "-aq", capture_output=True, text=True).stdout.strip()
if existing:
    raise SystemExit("Existing watchdog-test containers found; refusing to alter them")

def http(path, token=None, method="GET", data=None):
    request = urllib.request.Request("http://127.0.0.1:18088/" + path, method=method, data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer " + token} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code

def query(sql):
    # Read the password inside the test container; never include it in process arguments.
    php = "$c=require '/app/config.local.php'; require '/app/common.php'; database($c)->exec(" + json.dumps(sql) + ");"
    run("exec", "-T", "php", "php", "-r", php, capture_output=True)

def cron():
    result = run("exec", "-T", "php", "php", "-d", "sendmail_path=/bin/true", "cron.php",
                 capture_output=True, text=True)
    assert not result.stdout and not result.stderr, "Successful cron should produce no output"

try:
    run("up", "-d", "--build", "--wait")
    rejected = subprocess.run(compose + ["exec", "-T", "-e", "TEST_PASSWORD", "php", "php", "import-schema.php"],
        env=dict(env, TEST_PASSWORD="deliberately-wrong-test-password"), capture_output=True, text=True)
    assert rejected.returncode == 1
    assert "driver code=1045" in rejected.stderr and "rejected authentication" in rejected.stderr
    assert "deliberately-wrong-test-password" not in rejected.stderr
    assert env["TEST_PASSWORD"] not in rejected.stderr
    print("PASS: failed authentication reports a useful error without credentials")
    run("exec", "-T", "php", "php", "import-schema.php")
    query("UPDATE monitor SET notified_state='down' WHERE id=1")
    query("INSERT INTO check_history(checked_at,state) VALUES (UTC_TIMESTAMP(),'down')")
    run("exec", "-T", "php", "php", "import-schema.php")
    run("exec", "-T", "php", "php", "-r",
        "$c=require '/app/config.local.php'; require '/app/common.php'; $db=database($c);"
        "if ($db->query('SELECT notified_state FROM monitor WHERE id=1')->fetchColumn() !== 'down'"
        " || (int)$db->query('SELECT COUNT(*) FROM check_history')->fetchColumn() !== 1"
        " || (int)$db->query(\"SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='check_history' AND index_name='history_time'\")->fetchColumn() !== 1) exit(1);")
    print("PASS: fresh schema import and repeat import preserve state, history, and index")
    for attempt in range(30):
        try:
            assert http("") == 503
            break
        except (ConnectionError, urllib.error.URLError):
            time.sleep(1)
    assert http("heartbeat.php", method="POST") == 401
    assert http("heartbeat.php", env["TEST_TOKEN"]) == 405
    assert http("heartbeat.php", env["TEST_TOKEN"], "POST") == 204
    assert http("heartbeat.php", env["TEST_TOKEN"], "POST") == 429
    cron()
    cron()
    assert http("") == 200
    query("UPDATE monitor SET last_heartbeat = UTC_TIMESTAMP() - INTERVAL 10 MINUTE")
    cron()
    assert http("") == 503
    assert http("heartbeat.php", env["TEST_TOKEN"], "POST") == 204
    cron()
    assert http("") == 200
    query("UPDATE monitor SET checked_at = UTC_TIMESTAMP() - INTERVAL 10 MINUTE")
    assert http("") == 503
    print("PASS: watchdog authentication, throttling, heartbeat expiry, recovery and stale cron")
    backup_token = env["TEST_BACKUP_TOKEN"]
    assert http("backup.php", env["TEST_TOKEN"]) == 401
    assert http("heartbeat.php", backup_token, "POST") == 401
    assert http("backup.php", backup_token) == 200
    def scalar(sql):
        php = "$c=require '/app/config.local.php'; require '/app/common.php'; echo database($c)->query(" + json.dumps(sql) + ")->fetchColumn();"
        return run("exec", "-T", "php", "php", "-r", php, capture_output=True, text=True).stdout
    original_heartbeat = scalar('SELECT last_heartbeat FROM monitor WHERE id=1')
    start = int(time.time()) - 2
    event = {"run_id": "a" * 32, "started": start, "event": "success", "snapshot": "b" * 64}
    assert http("backup.php", backup_token, "POST", {**event, "started": int(time.time()) + 1000}) == 400
    assert http("backup.php", backup_token, "POST", event) == 204
    assert http("backup.php", backup_token, "POST", event) == 204
    assert scalar('SELECT last_heartbeat FROM monitor WHERE id=1') == original_heartbeat
    cron()
    assert scalar('SELECT state FROM backup_monitor WHERE id=1') == 'up'
    newer = {"run_id": "c" * 32, "started": start + 1, "event": "failure"}
    assert http("backup.php", backup_token, "POST", newer) == 204
    assert http("backup.php", backup_token, "POST", event) == 409
    run("exec", "-T", "php", "php", "-d", "sendmail_path=/bin/false", "cron.php", capture_output=True)
    assert scalar('SELECT notified_state FROM backup_monitor WHERE id=1') == 'up'
    cron()
    assert scalar('SELECT state FROM backup_monitor WHERE id=1') == 'down'
    assert int(scalar('SELECT last_capture FROM backup_monitor WHERE id=1')) == start
    query("UPDATE monitor SET last_heartbeat = UTC_TIMESTAMP() - INTERVAL 1 MINUTE")
    assert http("heartbeat.php", env["TEST_TOKEN"], "POST") == 204
    cron()
    assert scalar('SELECT state FROM backup_monitor WHERE id=1') == 'down'
    assert scalar('SELECT notified_state FROM backup_monitor WHERE id=1') == 'down'
    query("UPDATE backup_monitor SET outcome='success',last_capture=UNIX_TIMESTAMP()-86401")
    cron()
    assert scalar('SELECT state FROM backup_monitor WHERE id=1') == 'down'
    query("UPDATE backup_monitor SET last_capture=UNIX_TIMESTAMP(),running=1,started=UNIX_TIMESTAMP()-7201")
    cron()
    assert scalar('SELECT state FROM backup_monitor WHERE id=1') == 'down'
    recovery = {"run_id": "d" * 32, "started": int(time.time()), "event": "success", "snapshot": "e" * 64}
    assert http("backup.php", backup_token, "POST", recovery) == 204
    cron()
    assert scalar('SELECT notified_state FROM backup_monitor WHERE id=1') == 'up'
    run("exec", "-T", "php", "php", "import-schema.php")
    assert scalar('SELECT run_id FROM backup_monitor WHERE id=1') == 'd' * 32
    print('PASS: independent backup auth/state, replay protection, overdue/stalled detection, recovery and repeat migration')
finally:
    # Only the disposable test project and its anonymous database volume are removed.
    run("down", "--volumes")
