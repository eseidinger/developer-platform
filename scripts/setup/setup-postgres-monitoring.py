#!/usr/bin/env python3
"""Reconcile the dedicated PostgreSQL monitoring login without logging credentials."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
import subprocess

from scripts.internal.env import settings


def monitoring_sql(password):
    # SQL is sent on stdin, never in process arguments or diagnostic output.
    literal = "'" + password.replace("'", "''") + "'"
    return """
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'platform_monitor') THEN
   CREATE ROLE platform_monitor;
 END IF;
END $$;
ALTER ROLE platform_monitor LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 PASSWORD """ + literal + """;
GRANT pg_monitor TO platform_monitor;
GRANT CONNECT ON DATABASE platform TO platform_monitor;
DO $$ DECLARE target record; BEGIN
 IF to_regclass('public.store_resources') IS NOT NULL THEN
  FOR target IN SELECT d.datname FROM pg_database d JOIN public.store_resources r
   ON d.datname='resource_'||replace(r.resource_id::text,'-','')
   WHERE r.provider='postgresql' AND r.state<>'purged'
  LOOP EXECUTE format('GRANT CONNECT ON DATABASE %I TO platform_monitor',target.datname); END LOOP;
 END IF;
END $$;
ALTER ROLE platform_monitor SET default_transaction_read_only = on;
ALTER ROLE platform_monitor SET statement_timeout = '5s';
ALTER ROLE platform_monitor SET idle_in_transaction_session_timeout = '10s';
"""


def main():
    password = settings().get("POSTGRES_MONITOR_PASSWORD", "")
    if len(password) < 32 or "\x00" in password or "\n" in password or "\r" in password:
        raise SystemExit("Set a generated POSTGRES_MONITOR_PASSWORD using scripts/init.py")
    sql = monitoring_sql(password)
    result = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "platform"],
                            input=sql, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit("PostgreSQL monitoring role setup failed; check database availability and administrator access.")
    runtime = Path(".runtime")
    runtime.mkdir(mode=0o700, exist_ok=True)
    path = runtime / "postgres-monitor.password"
    # Preserve the inode so an existing read-only bind mount sees rotations.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(password)
    subprocess.run(["setfacl", "-b", str(path)], check=True)
    path.chmod(0o600)
    subprocess.run(["setfacl", "-m", "u:65534:r--", str(path)], check=True)
    print("PostgreSQL monitoring role and exporter credential ready.")


if __name__ == "__main__":
    main()
