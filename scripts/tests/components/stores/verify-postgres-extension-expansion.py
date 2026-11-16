#!/usr/bin/env python3
"""Exercise PLAN-040 against an isolated image; never connect to a live server."""

import itertools
import os
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "platform/app/src"))
from app.stores import catalog
from app.stores.postgres import Postgres

EXTENSIONS = ("vector", "age", "timescaledb", "postgis", "pgmq", "pg_duckdb")


def docker(*args):
    return subprocess.check_output(
        ("docker", *args), text=True, stderr=subprocess.STDOUT, timeout=180
    ).strip()


def wait_for_server(connect):
    last_error = None
    for _ in range(240):
        try:
            with connect("postgres"):
                return
        except psycopg.OperationalError as error:
            last_error = error
            time.sleep(0.5)
    raise AssertionError(f"Disposable PostgreSQL server did not start: {last_error}")


def assert_denied(connection, statement):
    try:
        connection.execute(statement)
    except psycopg.Error:
        return
    raise AssertionError(f"Unexpectedly permitted SQL: {statement}")


def main():
    container = "plan040-" + uuid4().hex[:12]
    password = secrets.token_urlsafe(24)
    os.environ["DATABASE_KEY"] = secrets.token_hex(32)
    image = os.environ.get(
        "NAMED_POSTGRES_IMAGE", "developer-platform-postgres:plan040"
    )
    restored_container = container + "-dumpall"

    try:
        started_at = time.monotonic()
        docker(
            "run",
            "-d",
            "--name",
            container,
            "--memory",
            "2g",
            "--cpus",
            "1",
            "--mount",
            f"type=volume,source={container}-data,target=/var/lib/postgresql",
            "-p",
            "127.0.0.1::5432",
            "-e",
            "POSTGRES_PASSWORD=" + password,
            image,
        )
        port = int(docker("port", container, "5432/tcp").rsplit(":", 1)[1])

        def connect(database):
            return psycopg.connect(
                host="127.0.0.1",
                port=port,
                dbname=database,
                user="postgres",
                password=password,
                autocommit=True,
                connect_timeout=3,
            )

        wait_for_server(connect)
        print(
            f"STARTUP ready in {time.monotonic() - started_at:.2f} seconds", flush=True
        )
        provider = Postgres(connect)
        with connect("postgres") as admin:
            available = {
                name: version
                for name, version in admin.execute(
                    "SELECT name,default_version FROM pg_available_extensions WHERE name=ANY(%s)",
                    (list(EXTENSIONS),),
                )
            }
            assert set(available) == set(EXTENSIONS), available
            print("Available extension versions:", available, flush=True)

            # Every advertised subset gets its own database. The final full
            # subset uses the normal provisioner and credential policy below.
            compatibility_databases = []
            for count in range(1, len(EXTENSIONS) + 1):
                for members in itertools.combinations(EXTENSIONS, count):
                    suffix = "".join(str(EXTENSIONS.index(name)) for name in members)
                    database = "compat_" + suffix
                    compatibility_databases.append(database)
                    admin.execute(
                        sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
                    )
                    with connect(database) as fixture:
                        for extension in members:
                            fixture.execute(
                                sql.SQL("CREATE EXTENSION {}").format(
                                    sql.Identifier(extension)
                                )
                            )
                        installed = {
                            row[0]
                            for row in fixture.execute(
                                "SELECT extname FROM pg_extension"
                            )
                        }
                        assert set(members).issubset(installed)
                    print("PASS subset", ",".join(members), flush=True)

            # The reverse order catches loader and object-creation ordering
            # conflicts that the ordinary provisioner cannot generate.
            admin.execute("CREATE DATABASE compat_reverse")
            with connect("compat_reverse") as fixture:
                try:
                    for extension in reversed(EXTENSIONS):
                        fixture.execute(
                            sql.SQL("CREATE EXTENSION {}").format(
                                sql.Identifier(extension)
                            )
                        )
                except psycopg.errors.DuplicateFunction as error:
                    assert 'function "time_bucket" already exists' in str(error)
                    print(
                        "LIMITATION reverse creation: pg_duckdb before TimescaleDB "
                        "collides on time_bucket",
                        flush=True,
                    )
                else:
                    print("PASS reverse creation", flush=True)
            compatibility_databases.append("compat_reverse")
            for database in compatibility_databases:
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(database)
                    )
                )

            # API clients may send any order; the provider must normalize it.
            resource = {
                "resource_id": uuid4(),
                "extensions": list(reversed(EXTENSIONS)),
            }
            plain = {"resource_id": uuid4(), "extensions": []}
            provider.provision(resource)
            provider.provision(plain)
            database = catalog.identifier(resource["resource_id"])
            plain_database = catalog.identifier(plain["resource_id"])
            with connect(plain_database) as fixture:
                assert not set(EXTENSIONS).intersection(
                    name
                    for (name,) in fixture.execute("SELECT extname FROM pg_extension")
                )

            issued = []
            for mode in ("read-write", "read-only"):
                credential = {
                    "credential_id": uuid4(),
                    "mode": mode,
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                }
                provider.issue(resource, credential)
                issued.append(credential)

            def login(credential, target=database):
                return psycopg.connect(
                    host="127.0.0.1",
                    port=port,
                    dbname=target,
                    user=catalog.login(credential["credential_id"]),
                    password=catalog.secret_for(credential["credential_id"]),
                    autocommit=True,
                    connect_timeout=3,
                )

            writer, reader = issued
            with login(writer) as connection:
                connection.execute(
                    "CREATE TABLE public.measurements(time timestamptz NOT NULL, value int)"
                )
                connection.execute(
                    "SELECT create_hypertable('measurements', by_range('time'))"
                )
                connection.execute("INSERT INTO public.measurements VALUES(now(), 42)")
                assert (
                    connection.execute(
                        "SELECT sum(value) FROM public.measurements"
                    ).fetchone()[0]
                    == 42
                )
                connection.execute(
                    "CREATE TABLE public.places(id int, point geometry(Point,4326))"
                )
                connection.execute(
                    "INSERT INTO public.places VALUES(1, ST_SetSRID(ST_MakePoint(13,52),4326))"
                )
                assert (
                    connection.execute(
                        "SELECT ST_X(point) FROM public.places"
                    ).fetchone()[0]
                    == 13
                )
                connection.execute("SELECT pgmq.create('jobs')")
                connection.execute("SELECT pgmq.send('jobs', '{\"task\":1}'::jsonb)")
                assert (
                    connection.execute("SELECT count(*) FROM pgmq.q_jobs").fetchone()[0]
                    == 1
                )
                assert (
                    connection.execute(
                        "SELECT * FROM duckdb.query('SELECT 42 AS answer')"
                    ).fetchone()[0]
                    == 42
                )
                assert_denied(
                    connection,
                    "SELECT * FROM duckdb.query('SELECT * FROM read_text(''/etc/passwd'')')",
                )
                assert_denied(connection, "SELECT duckdb.raw_query('SELECT 1')")

            with login(reader) as connection:
                assert (
                    connection.execute(
                        "SELECT sum(value) FROM public.measurements"
                    ).fetchone()[0]
                    == 42
                )
                assert (
                    connection.execute(
                        "SELECT ST_X(point) FROM public.places"
                    ).fetchone()[0]
                    == 13
                )
                assert_denied(
                    connection, "INSERT INTO public.measurements VALUES(now(), 1)"
                )
                assert_denied(connection, "SELECT pgmq.send('jobs', '{}'::jsonb)")
                assert_denied(connection, "SELECT * FROM duckdb.query('SELECT 1')")

            try:
                with login(writer, plain_database):
                    raise AssertionError(
                        "Selected-resource writer entered plain database"
                    )
            except psycopg.OperationalError:
                pass

            docker("restart", container)
            # Docker may assign a new ephemeral host port after restart.
            port = int(docker("port", container, "5432/tcp").rsplit(":", 1)[1])
            wait_for_server(connect)
            with login(writer) as connection:
                assert (
                    connection.execute(
                        "SELECT sum(value) FROM public.measurements"
                    ).fetchone()[0]
                    == 42
                )
                assert (
                    connection.execute("SELECT count(*) FROM pgmq.q_jobs").fetchone()[0]
                    == 1
                )
                assert (
                    connection.execute(
                        "SELECT * FROM duckdb.query('SELECT 42 AS answer')"
                    ).fetchone()[0]
                    == 42
                )
            print("PASS roles, workloads, isolation, restart", flush=True)

            # Measure a bounded mixed workload with the same one-CPU/two-GiB
            # container limit as the deployed service. Keep benchmark rows in
            # separate tables so the recovery assertions remain exact.
            cpu_before = int(
                next(
                    line.split()[1]
                    for line in docker(
                        "exec", container, "cat", "/sys/fs/cgroup/cpu.stat"
                    ).splitlines()
                    if line.startswith("usage_usec ")
                )
            )
            workload_started_at = time.monotonic()
            with login(writer) as connection:
                connection.execute(
                    "CREATE TABLE public.bench_measurements(time timestamptz NOT NULL, value int)"
                )
                connection.execute(
                    "SELECT create_hypertable('bench_measurements', by_range('time'))"
                )
                connection.execute("""INSERT INTO public.bench_measurements
                    SELECT now() - interval '1 second' * n, n
                    FROM generate_series(1,100000) AS n""")
                connection.execute(
                    "CREATE TABLE public.bench_places(id int, point geometry(Point,4326))"
                )
                connection.execute("""INSERT INTO public.bench_places
                    SELECT n, ST_SetSRID(ST_MakePoint(n % 360, n % 180),4326)
                    FROM generate_series(1,10000) AS n""")
                connection.execute(
                    "CREATE INDEX ON public.bench_places USING gist(point)"
                )
                connection.execute("SELECT pgmq.create('bench_jobs')")
                connection.execute("""SELECT pgmq.send('bench_jobs', jsonb_build_object('n',n))
                    FROM generate_series(1,100) AS n""")
                assert (
                    connection.execute(
                        "SELECT count(*) FROM public.bench_measurements"
                    ).fetchone()[0]
                    == 100000
                )
                assert (
                    connection.execute(
                        "SELECT count(*) FROM public.bench_places WHERE ST_X(point) >= 0"
                    ).fetchone()[0]
                    == 10000
                )
                assert (
                    connection.execute(
                        "SELECT count(*) FROM pgmq.q_bench_jobs"
                    ).fetchone()[0]
                    == 100
                )
                assert (
                    connection.execute(
                        "SELECT * FROM duckdb.query('SELECT sum(i) FROM generate_series(1,1000000) t(i)')"
                    ).fetchone()[0]
                    == 500000500000
                )
            workload_seconds = time.monotonic() - workload_started_at
            cpu_after = int(
                next(
                    line.split()[1]
                    for line in docker(
                        "exec", container, "cat", "/sys/fs/cgroup/cpu.stat"
                    ).splitlines()
                    if line.startswith("usage_usec ")
                )
            )
            memory_peak = int(
                docker("exec", container, "cat", "/sys/fs/cgroup/memory.peak")
            )
            with connect("postgres") as fixture:
                workload_disk_bytes = fixture.execute(
                    "SELECT pg_database_size(%s)", (database,)
                ).fetchone()[0]
            assert memory_peak < 2 * 1024**3
            print(
                "COST mixed workload "
                f"wall={workload_seconds:.2f}s cpu={(cpu_after - cpu_before) / 1_000_000:.2f}s "
                f"memory_peak={memory_peak} bytes database={workload_disk_bytes} bytes",
                flush=True,
            )

            # A logical dump must restore actual queue/time-series/spatial
            # state, not merely extension catalog entries. Timescale's restore
            # hooks prevent its background jobs from acting on partial data.
            with tempfile.TemporaryFile() as archive:
                subprocess.run(
                    (
                        "docker",
                        "exec",
                        container,
                        "pg_dump",
                        "-U",
                        "postgres",
                        "-Fc",
                        database,
                    ),
                    check=True,
                    stdout=archive,
                )
                archive.seek(0)
                with connect("postgres") as fixture:
                    fixture.execute(
                        "CREATE DATABASE compat_restored TEMPLATE template0"
                    )
                with connect("compat_restored") as fixture:
                    fixture.execute("CREATE EXTENSION timescaledb")
                    fixture.execute("SELECT timescaledb_pre_restore()")
                subprocess.run(
                    (
                        "docker",
                        "exec",
                        "-i",
                        container,
                        "pg_restore",
                        "-U",
                        "postgres",
                        "-d",
                        "compat_restored",
                        "--exit-on-error",
                    ),
                    check=True,
                    stdin=archive,
                    stdout=subprocess.DEVNULL,
                )
                with connect("compat_restored") as fixture:
                    fixture.execute("SELECT timescaledb_post_restore()")
                    fixture.execute("SET search_path=public,platform_extensions")
                    assert (
                        fixture.execute(
                            "SELECT sum(value) FROM public.measurements"
                        ).fetchone()[0]
                        == 42
                    )
                    assert (
                        fixture.execute(
                            "SELECT ST_X(point) FROM public.places"
                        ).fetchone()[0]
                        == 13
                    )
                    assert (
                        fixture.execute("SELECT count(*) FROM pgmq.q_jobs").fetchone()[
                            0
                        ]
                        == 1
                    )
                    assert (
                        fixture.execute(
                            "SELECT * FROM duckdb.query('SELECT 42 AS answer')"
                        ).fetchone()[0]
                        == 42
                    )
            print("PASS combined logical restore", flush=True)
            with connect("postgres") as fixture:
                disk_bytes = fixture.execute(
                    "SELECT pg_database_size(%s)", (database,)
                ).fetchone()[0]
            statistics = docker(
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}} {{.MemUsage}}",
                container,
            )
            print(
                f"COST full resource database={disk_bytes} bytes, container={statistics}",
                flush=True,
            )

            # The production backup streams pg_dumpall rather than custom
            # per-database archives. Check that format in a fresh server too.
            docker(
                "run",
                "-d",
                "--name",
                restored_container,
                "--memory",
                "2g",
                "--cpus",
                "1",
                "-e",
                "POSTGRES_PASSWORD=" + password,
                image,
            )
            for _ in range(120):
                result = subprocess.run(
                    (
                        "docker",
                        "exec",
                        restored_container,
                        "pg_isready",
                        "-U",
                        "postgres",
                    ),
                    capture_output=True,
                    check=False,
                )
                if result.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise AssertionError("pg_dumpall restore target did not start")
            with tempfile.TemporaryFile() as archive:
                subprocess.run(
                    ("docker", "exec", container, "pg_dumpall", "-U", "postgres"),
                    check=True,
                    stdout=archive,
                )
                archive.seek(0)
                result = subprocess.run(
                    (
                        "docker",
                        "exec",
                        "-i",
                        restored_container,
                        "psql",
                        "-X",
                        "-U",
                        "postgres",
                        "-d",
                        "postgres",
                    ),
                    check=False,
                    stdin=archive,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                diagnostics = result.stderr.decode().splitlines()
                allowed = {
                    'ERROR:  role "postgres" already exists',
                    'ERROR:  database "postgres" already exists',
                    (
                        "WARNING:  time_bucket function already exists, use "
                        "duckdb.time_bucket instead. This is usually because "
                        "the timescale extension is installed."
                    ),
                }
                unexpected = [line for line in diagnostics if line not in allowed]
                if result.returncode or unexpected:
                    raise AssertionError(
                        "pg_dumpall restore emitted unexpected diagnostics: "
                        + repr(unexpected[:8])
                    )
            for statement, expected in (
                ("SELECT sum(value) FROM public.measurements", "42"),
                ("SELECT count(*) FROM pgmq.q_jobs", "1"),
                ("SELECT ST_X(point) FROM public.places", "13"),
                ("SELECT * FROM duckdb.query('SELECT 42 AS answer')", "42"),
            ):
                value = docker(
                    "exec",
                    restored_container,
                    "psql",
                    "-X",
                    "-U",
                    "postgres",
                    "-d",
                    database,
                    "-At",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    "SET search_path=public,platform_extensions; " + statement,
                ).splitlines()[-1]
                assert value == expected, (statement, value)
            print("PASS production-format pg_dumpall restore", flush=True)
    finally:
        subprocess.run(
            ("docker", "rm", "-f", "-v", restored_container),
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ("docker", "rm", "-f", container), check=False, capture_output=True
        )
        subprocess.run(
            ("docker", "volume", "rm", f"{container}-data"),
            check=False,
            capture_output=True,
        )


if __name__ == "__main__":
    main()
