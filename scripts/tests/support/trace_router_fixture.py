"""Run the production trace router against a disposable, read-only SQL catalog."""

import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from app import telemetry_catalog


def free_port():
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return stream.getsockname()[1]


@contextmanager
def router(tempo_url):
    """Only fixture-owned PostgreSQL and the router subprocess are cleaned up."""
    name = "trace-catalog-" + uuid4().hex[:12]
    password = secrets.token_hex(32)
    tenant = str(uuid4())
    process = None
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--memory",
                "256m",
                "--cpus",
                "1",
                "--tmpfs",
                "/var/lib/postgresql:rw,size=128m",
                "-e",
                "POSTGRES_DB=platform",
                "-e",
                "POSTGRES_PASSWORD",
                "-p",
                "127.0.0.1::5432",
                "postgres:18.6-trixie",
            ],
            env={**os.environ, "POSTGRES_PASSWORD": password},
            check=True,
            capture_output=True,
            timeout=180,
        )
        port = (
            subprocess.check_output(
                ["docker", "port", name, "5432/tcp"], text=True, timeout=10
            )
            .strip()
            .rsplit(":", 1)[1]
        )
        for attempt in range(120):
            try:
                connection = psycopg.connect(
                    host="127.0.0.1",
                    port=port,
                    dbname="platform",
                    user="postgres",
                    password=password,
                    autocommit=True,
                    connect_timeout=2,
                )
                break
            except psycopg.OperationalError:
                if attempt == 119:
                    raise
                time.sleep(0.25)
        with connection as conn:
            conn.execute(
                "CREATE TABLE projects(name TEXT, project_id UUID, status TEXT, spec JSONB)"
            )
            conn.execute(
                "CREATE TABLE project_lifecycle_operations(project_id UUID, state TEXT)"
            )
            conn.execute(
                "INSERT INTO projects VALUES ('fixture-ai',%s,'applied','{}')",
                (tenant,),
            )
            # Use the production views and permissions, rather than granting
            # the router superuser access or replacing its project lookup.
            previous = os.environ.get("TELEMETRY_CATALOG_PASSWORD")
            os.environ["TELEMETRY_CATALOG_PASSWORD"] = password
            try:
                telemetry_catalog.initialize(conn)
            finally:
                if previous is None:
                    os.environ.pop("TELEMETRY_CATALOG_PASSWORD", None)
                else:
                    os.environ["TELEMETRY_CATALOG_PASSWORD"] = previous
        router_port = free_port()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.trace_router:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(router_port),
                "--no-access-log",
            ],
            env={
                **os.environ,
                "POSTGRES_HOST": "127.0.0.1",
                "PGPORT": port,
                "TELEMETRY_CATALOG_PASSWORD": password,
                "TEMPO_OTLP_URL": tempo_url,
            },
        )
        url = f"http://127.0.0.1:{router_port}"
        for attempt in range(120):
            if process.poll() is not None:
                raise RuntimeError("Disposable trace router exited before readiness")
            try:
                with urllib.request.urlopen(url + "/healthz", timeout=1):
                    break
            except OSError:
                if attempt == 119:
                    raise
                time.sleep(0.25)
        yield url, tenant
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            capture_output=True,
            timeout=30,
            check=False,
        )
