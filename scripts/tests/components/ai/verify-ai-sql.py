#!/usr/bin/env python3
"""Run AI SQL contracts in a fresh database on an explicitly selected test server.

AI_FIXTURE_TEST_DSN must identify a disposable PostgreSQL server where the test
user may create databases. No configured platform database or model is used.
"""

import json
import os
import runpy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app import ai_changes, ai_store, main
from psycopg import sql


def verify():
    dsn = os.environ.get("AI_FIXTURE_TEST_DSN")
    if not dsn:
        raise SystemExit(
            "Set AI_FIXTURE_TEST_DSN to an isolated test PostgreSQL server"
        )
    database = "ai_fixture_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:

            def connect():
                return psycopg.connect(dsn, dbname=database, autocommit=True)

            with connect() as conn:
                conn.execute("CREATE TABLE projects(name TEXT PRIMARY KEY)")
                ai_store.initialize(conn)
                ai_changes.initialize(conn)
            results = {}
            with patch.object(main, "connect", connect):
                for name in ("approval-guards", "portal-history"):
                    module = runpy.run_path(
                        str(Path(__file__).with_name("verify-ai-" + name + ".py"))
                    )
                    results[name] = module["verify"]()
            return results
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database)
                )
            )


if __name__ == "__main__":
    print(json.dumps(verify()))
