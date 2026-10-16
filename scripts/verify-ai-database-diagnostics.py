#!/usr/bin/env python3
"""Verify real driver error formats with no project data or network access.

UV_CACHE_DIR=/tmp/uvcache uv run --project platform/app --no-sync \
  --with sqlalchemy==2.0.46 python scripts/verify-ai-database-diagnostics.py

SQLAlchemy is a verification-only dependency, not a platform runtime dependency.
"""
import json
import socket
from unittest.mock import patch

import psycopg
from psycopg import _conninfo_attempts
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.pool import QueuePool

from app.ai_diagnostics import failure_codes


def verify():
    with patch.object(_conninfo_attempts, "_resolve_hostnames",
                      side_effect=socket.gaierror(-2, "Name or service not known")):
        try:
            _conninfo_attempts.conninfo_attempts({"host": "synthetic.invalid"})
        except psycopg.OperationalError as error:
            assert failure_codes(str(error).encode()) == ["database_hostname_resolution_failed"]
        else:
            raise AssertionError("Expected driver resolution failure")
    engine = create_engine("sqlite://", poolclass=QueuePool, pool_size=1,
                           max_overflow=0, pool_timeout=0.01)
    try:
        with engine.connect():
            try:
                engine.connect()
            except PoolTimeout as error:
                assert failure_codes(str(error).encode()) == ["database_pool_capacity_timeout"]
            else:
                raise AssertionError("Expected real pool capacity timeout")
    finally:
        engine.dispose()
    return {"psycopg_error_format_verified": True, "real_pool_timeout_verified": True,
            "network_requests": 0, "project_data_used": False}


if __name__ == "__main__":
    print(json.dumps(verify()))
