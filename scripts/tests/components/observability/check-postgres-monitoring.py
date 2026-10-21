#!/usr/bin/env python3
"""Exercise production PostgreSQL monitoring with disposable PostgreSQL/exporter/Prometheus."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[4]


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kwargs)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(check):
    for _ in range(150):
        try:
            if check():
                return
        except (OSError, subprocess.CalledProcessError):
            pass
        time.sleep(.2)
    raise AssertionError("PostgreSQL monitoring fixture did not converge")


def main():
    context = run("docker", "context", "show").strip()
    endpoint = run("docker", "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}").strip()
    if os.environ.get("DOCKER_HOST", endpoint) != "unix:///var/run/docker.sock":
        raise RuntimeError("Fixture requires the local Linux Docker socket")
    name = "platform-pg-metrics-" + uuid.uuid4().hex[:10]
    exporter, prometheus = name + "-exporter", name + "-prometheus"
    export_port, prom_port = free_port(), free_port()
    config = ROOT / "infrastructure/monitoring"
    service = yaml.safe_load((config / "compose.yaml").read_text())["services"]["postgres-exporter"]
    spec = importlib.util.spec_from_file_location("pg_setup", ROOT / "scripts/setup/setup-postgres-monitoring.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)

    def sql(text, database="platform", user="postgres", check=True):
        return subprocess.run(["docker", "exec", "-i", name, "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", database],
                              input=text, text=True, capture_output=True, check=check)

    def query(expression):
        url = f"http://127.0.0.1:{prom_port}/api/v1/query?" + urllib.parse.urlencode({"query": expression})
        return json.load(urllib.request.urlopen(url, timeout=3))["data"]["result"]

    try:
        with tempfile.TemporaryDirectory(prefix="platform-pg-metrics-") as directory:
            temp = Path(directory)
            temp.chmod(0o755)
            password = "fixture-only-monitoring-password-123456789"
            (temp / "password").write_text(password)
            (temp / "password").chmod(0o644)  # Disposable fixture credential only.
            run("docker", "network", "create", name)
            run("docker", "run", "--rm", "-d", "--name", name, "--network", name,
                "--network-alias", "postgres", "-e", "POSTGRES_PASSWORD=fixture-only-admin", "-e", "POSTGRES_DB=platform", "postgres:18.6-trixie")
            # The image's temporary initialization server uses only Unix sockets.
            wait_for(lambda: subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "platform"], capture_output=True).returncode == 0)
            sql(setup.monitoring_sql(password))
            sql(setup.monitoring_sql(password))  # Existing-database bootstrap is repeatable.
            sql("CREATE DATABASE project_fixture_a; CREATE DATABASE project_fixture_b;")
            sql("CREATE TABLE private_fixture (secret text); INSERT INTO private_fixture VALUES ('fixture-private-payload');")
            assert sql("SELECT * FROM private_fixture;", user="platform_monitor", check=False).returncode != 0
            assert sql("CREATE TABLE forbidden_fixture(i int);", user="platform_monitor", check=False).returncode != 0
            role = sql("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolconnlimit,pg_has_role(oid,'pg_monitor','MEMBER') FROM pg_roles WHERE rolname='platform_monitor';").stdout.strip()
            assert role == "f|f|f|f|f|5|t", role
            env = service["environment"]
            run("docker", "run", "--rm", "-d", "--name", exporter, "--network", name,
                "-p", f"127.0.0.1:{export_port}:9187", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "-v", f"{temp / 'password'}:/run/secrets/postgres-monitor.password:ro",
                "-v", f"{config / 'postgres-queries.yaml'}:/etc/postgres-exporter/queries.yaml:ro",
                *[item for k, v in env.items() for item in ("-e", f"{k}={v}")], service["image"], *service["command"])
            job = copy.deepcopy(next(x for x in yaml.safe_load((config / "prometheus.yaml").read_text())["scrape_configs"] if x["job_name"] == "postgres"))
            job.update(scrape_interval="1s", scrape_timeout="1s", static_configs=[{"targets": [f"127.0.0.1:{export_port}"]}])
            (temp / "prometheus.yml").write_text(yaml.safe_dump({"scrape_configs": [job]}))
            run("docker", "run", "--rm", "-d", "--name", prometheus, "--network", "host",
                "-v", f"{temp}:/etc/prometheus:ro", "prom/prometheus:v3.14.0", "--config.file=/etc/prometheus/prometheus.yml",
                "--storage.tsdb.path=/tmp/data", f"--web.listen-address=127.0.0.1:{prom_port}")
            wait_for(lambda: bool(query('pg_up{job="postgres"} == 1')))
            wait_for(lambda: bool(query('rate(pg_stat_database_xact_commit{job="postgres",datname="platform"}[5m])')))
            assert query('pg_exporter_last_scrape_error{job="postgres"}')[0]["value"][1] == "0"
            databases = query('pg_database_size_bytes{job="postgres"}')
            assert {"platform", "project_fixture_a", "project_fixture_b"} <= {x["metric"]["datname"] for x in databases}
            # Generate real block reads, transactions and a rollback in the selected database.
            sql("SELECT * FROM private_fixture; BEGIN; SELECT 1; ROLLBACK;")
            time.sleep(2)
            dashboard = json.loads((config / "dashboards/postgresql.json").read_text())
            for panel in dashboard["panels"]:
                results = [row for target in panel["targets"] for row in query(target["expr"].replace("$database", "platform"))]
                if panel["title"] not in {"Database configured connection limit", "Database buffer cache hit ratio"}:
                    assert results, panel["title"]
            for database in ("project_fixture_a", "project_fixture_b"):
                for metric in ("pg_database_size_bytes", "pg_stat_database_numbackends", "pg_platform_activity_connections"):
                    values = query(f'{metric}{{job="postgres",datname="{database}"}}')
                    assert values and all(x["metric"]["datname"] == database for x in values)
            assert not query('pg_database_connection_limit{job="postgres",datname="platform"} > 0')
            assert not query('pg_database_size_bytes{job="postgres",datname="missing"}')
            for row in query('{job="postgres",__name__=~"pg_.*"}'):
                assert set(row["metric"]) <= {"__name__", "job", "instance", "datname", "state", "mode"}, row
            raw = urllib.request.urlopen(f"http://127.0.0.1:{export_port}/metrics").read().decode()
            assert "pg_stat_statements" not in raw and "private_fixture" not in raw and "fixture-private-payload" not in raw
            assert "usename=" not in raw and "application_name=" not in raw
            # A stopped collector must become unavailable and recover after restart.
            run("docker", "pause", exporter)
            try:
                wait_for(lambda: bool(query('up{job="postgres"} == 0')))
            finally:
                run("docker", "unpause", exporter)
            wait_for(lambda: bool(query('pg_up{job="postgres"} == 1')))
            print("PASS PostgreSQL 18 monitoring permissions, idempotent setup, aggregate privacy, database selection, dashboard queries and collector outage/recovery")
    finally:
        for container in (prometheus, exporter, name):
            subprocess.run(["docker", "rm", "-f", "-v", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "network", "rm", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
