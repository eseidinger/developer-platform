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
env = dict(os.environ, TEST_PASSWORD=secrets.token_hex(24), TEST_TOKEN=secrets.token_hex(32))
compose = ["docker", "compose", "-p", "platform-watchdog-test", "-f", "tests/compose.watchdog.yaml"]
def run(*args, **kwargs):
    return subprocess.run(compose + list(args), env=env, check=True, **kwargs)
existing = run("ps", "-aq", capture_output=True, text=True).stdout.strip()
if existing:
    raise SystemExit("Existing watchdog-test containers found; refusing to alter them")

def http(path, token=None, method="GET"):
    request = urllib.request.Request("http://127.0.0.1:18088/" + path, method=method,
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
    run("exec", "-T", "php", "php", "-d", "sendmail_path=/bin/true", "cron.php")

try:
    run("up", "-d", "--build", "--wait")
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
finally:
    # Only the disposable test project and its anonymous database volume are removed.
    run("down", "--volumes")
