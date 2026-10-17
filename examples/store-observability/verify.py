"""Actual DuckDB profiling -> allowlisted workload metrics; no private payload output."""
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4
import duckdb
from metrics import StoreMetrics


def main():
    metrics=StoreMetrics(uuid4(),'duckdb')
    with tempfile.TemporaryDirectory(prefix='duckdb-observability-') as directory:
        root=Path(directory);root.chmod(0o700)
        previous=os.umask(0o077)
        try:
            with duckdb.connect(config={'threads':2,'memory_limit':'128MB'}) as conn:
                output=root/'profile.json'
                conn.execute("PRAGMA enable_profiling='json'")
                conn.execute('SET profiling_output = ?', [str(output)])
                with metrics.operation('query'):
                    rows=conn.execute('SELECT sum(i) FROM range(1024) t(i) /* private-query-marker */').fetchall()
                assert rows==[(523776,)]
                profile=json.loads(output.read_text())
                assert 'private-query-marker' in json.dumps(profile)
                metrics.duckdb_profile(profile)
        finally:os.umask(previous)
    text=metrics.exposition()
    assert 'private-query-marker' not in text and 'profile.json' not in text
    for name in ['cpu_seconds','peak_memory_bytes','spill_bytes','rows_scanned','rows_returned','duration_seconds_bucket']:
        assert 'platform_store_workload_'+name in text
    print('PASS actual DuckDB 1.5 profiling and query histogram export; SQL, paths and operator payloads excluded')

if __name__=='__main__':
    try:main()
    except Exception as error:raise SystemExit('DuckDB observability fixture failed ('+type(error).__name__+')') from None
