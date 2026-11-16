#!/usr/bin/env python3
"""Rehearse old -> new -> old image switching on a disposable PG18 volume."""

import os
import secrets
import subprocess
import time
from uuid import uuid4

OLD_IMAGE = "developer-platform-postgres:18.6-vector0.8.7-age1.8.0"
NEW_IMAGE = "developer-platform-postgres:plan040"


def docker(*arguments):
    return subprocess.check_output(
        ("docker", *arguments), text=True, stderr=subprocess.STDOUT, timeout=120
    ).strip()


def sql(container, statement):
    return docker(
        "exec",
        container,
        "psql",
        "-X",
        "-U",
        "postgres",
        "-d",
        "rollback_fixture",
        "-At",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        statement,
    )


def start(container, volume, image, password):
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
        f"type=volume,source={volume},target=/var/lib/postgresql",
        "-e",
        "POSTGRES_PASSWORD=" + password,
        image,
    )
    for _ in range(120):
        result = subprocess.run(
            ("docker", "exec", container, "pg_isready", "-U", "postgres"),
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise AssertionError(f"PostgreSQL image did not start: {image}")


def assert_data(container):
    assert (
        sql(
            container,
            "SELECT id FROM measurements ORDER BY embedding <-> '[1,2,3]'::vector LIMIT 1",
        )
        == "1"
    )
    assert (
        sql(container, "SELECT count(*) FROM pg_extension WHERE extname='vector'")
        == "1"
    )


def main():
    suffix = uuid4().hex[:12]
    container = "plan040-rollback-" + suffix
    volume = container + "-data"
    password = secrets.token_urlsafe(24)
    old_image = os.environ.get("PLAN040_OLD_IMAGE", OLD_IMAGE)
    new_image = os.environ.get("PLAN040_NEW_IMAGE", NEW_IMAGE)
    try:
        start(container, volume, old_image, password)
        docker("exec", container, "createdb", "-U", "postgres", "rollback_fixture")
        sql(container, "CREATE EXTENSION vector")
        sql(container, "CREATE TABLE measurements(id int, embedding vector(3))")
        sql(container, "INSERT INTO measurements VALUES(1,'[1,2,3]')")
        assert_data(container)
        docker("rm", "-f", container)

        start(container, volume, new_image, password)
        assert_data(container)
        assert (
            sql(
                container, "SELECT count(*) FROM pg_extension WHERE extname='pg_duckdb'"
            )
            == "0"
        )
        docker("rm", "-f", container)

        start(container, volume, old_image, password)
        assert_data(container)
        print("PASS old -> new -> old image rollback with retained vector data")
    finally:
        subprocess.run(
            ("docker", "rm", "-f", container), capture_output=True, check=False
        )
        subprocess.run(
            ("docker", "volume", "rm", volume), capture_output=True, check=False
        )


if __name__ == "__main__":
    main()
