"""Opt-in application analytics fixtures; no DuckDB dependency in the API image."""
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal
import io
import json
from pathlib import Path
import sys
import tempfile
import time

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples/analytics-artifacts'))
from artifacts import Artifacts, ObjectVersion

QUERIES = {
    'daily': 'SELECT day,SUM(energy_kwh) FROM facts GROUP BY day ORDER BY day',
    'monthly': "SELECT CAST(date_trunc('month',day) AS DATE),SUM(energy_kwh) FROM facts GROUP BY 1 ORDER BY 1",
    'weather_join': '''SELECT f.day,w.temperature_c,SUM(f.energy_kwh) FROM facts f
        JOIN (SELECT DISTINCT day,temperature_c FROM facts) w ON w.day=f.day
        GROUP BY f.day,w.temperature_c ORDER BY f.day''',
    'running_total': '''SELECT day,SUM(SUM(energy_kwh)) OVER(ORDER BY day ROWS UNBOUNDED PRECEDING)
        FROM facts GROUP BY day ORDER BY day''',
    'scenario_cost': '''SELECT site,CAST(SUM(energy_kwh*price_cents)*1.2/100 AS DECIMAL(18,2))
        FROM facts GROUP BY site ORDER BY site''',
}


def rows():
    return [(date(2026, 1, 1) + timedelta(days=n), site, 100 + n, 5, n % 20)
            for n in range(90) for site in ('alpha', 'beta')]


def normalize(result):
    return [tuple(value.isoformat() if isinstance(value, date) else
        format(Decimal(str(value)).normalize(), 'f') if isinstance(value, (int, Decimal)) else value
        for value in row) for row in result]


def oracle():
    daily, monthly, costs, temperatures = defaultdict(int), defaultdict(int), defaultdict(int), {}
    for day, site, energy, price, temperature in rows():
        daily[day] += energy
        monthly[day.replace(day=1)] += energy
        costs[site] += energy * price
        temperatures[day] = temperature
    running, total = [], 0
    for day, energy in sorted(daily.items()):
        total += energy
        running.append((day, total))
    return {key: normalize(value) for key, value in {
        'daily': sorted(daily.items()), 'monthly': sorted(monthly.items()),
        'weather_join': [(day, temperatures[day], energy) for day, energy in sorted(daily.items())],
        'running_total': running,
        'scenario_cost': [(site, Decimal(cost) * Decimal('.012')) for site, cost in sorted(costs.items())],
    }.items()}


def engine():
    return duckdb.connect(config={'threads': 2, 'memory_limit': '256MB',
        'autoinstall_known_extensions': 'false', 'autoload_known_extensions': 'false'})


def dataset(path):
    with engine() as conn:
        conn.execute('CREATE TABLE facts(day DATE,site VARCHAR,energy_kwh INTEGER,price_cents INTEGER,temperature_c INTEGER)')
        conn.executemany('INSERT INTO facts VALUES(?,?,?,?,?)', rows())
        check(conn, 'duckdb-memory')
        conn.execute("COPY facts TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)])


def check(conn, label):
    timings = {}
    expected = oracle()
    for name, query in QUERIES.items():
        start = time.perf_counter()
        result = normalize(conn.execute(query).fetchall())
        timings[name] = round((time.perf_counter() - start) * 1000, 3)
        assert result == expected[name], label + ' ' + name + ' differs from the Python oracle'
    print(json.dumps({'fixture': 'synthetic-energy-v1', 'engine': label, 'rows': len(rows()),
        'query_ms': timings}, sort_keys=True))


def check_parquet(path, label):
    with engine() as conn:
        conn.read_parquet(str(path)).create_view('facts')
        check(conn, label)


def publish(writer, reader, bucket):
    with tempfile.TemporaryDirectory(prefix='parquet-fixture-') as directory:
        root = Path(directory)
        source = root / 'source.parquet'
        dataset(source)
        check_parquet(source, 'duckdb-local-parquet')
        artifacts = Artifacts(writer, bucket)
        reference = artifacts.publish(source)
        # The serialized reference contains public identifiers/checksum only.
        reference = ObjectVersion(**json.loads(json.dumps(asdict(reference))))
        manifest = io.BytesIO()
        artifacts._read(reference, manifest, 65536)
        data = ObjectVersion(**json.loads(manifest.getvalue())['object'])
        # New versions at the same keys cannot silently change a published view.
        writer.put_object(Bucket=bucket, Key=data.key, Body=b'later data')
        writer.put_object(Bucket=bucket, Key=reference.key, Body=b'later manifest')
        start = time.perf_counter()
        restored = Artifacts(reader, bucket).materialize(reference, root / 'verified.parquet')
        print(json.dumps({'fixture': 'synthetic-energy-v1', 'operation': 's3-versioned-download-checksum',
            'parquet_bytes': data.bytes, 'transfer_ms': round((time.perf_counter() - start) * 1000, 3)}, sort_keys=True))
        check_parquet(restored, 'duckdb-versioned-s3-parquet')
        for invalid in (replace(reference, sha256='0' * 64), replace(reference, bytes=reference.bytes + 1),
                replace(reference, version_id='null')):
            try:
                Artifacts(reader, bucket).materialize(invalid, root / 'denied.parquet')
            except ValueError:
                assert not (root / 'denied.parquet').exists()
            else:
                raise AssertionError('Invalid artifact reference was accepted')
        print('PASS versioned Parquet publication, immutable reference readback, streaming SHA-256, manifest/size/version denial and no partial output')
        return reference


def recovered(reader, bucket, reference):
    with tempfile.TemporaryDirectory(prefix='restored-parquet-') as directory:
        path = Artifacts(reader, bucket).materialize(reference, Path(directory) / 'restored.parquet')
        check_parquet(path, 'duckdb-restored-s3-parquet')
    print('PASS exact manifest/data versions and analytical results after empty-volume restore and fresh read-only approval')


def postgres(conn):
    # Resource-scoped application connection, no server extension or privilege.
    with conn.transaction():
        conn.execute('CREATE TEMP TABLE facts(day DATE,site TEXT,energy_kwh INTEGER,price_cents INTEGER,temperature_c INTEGER) ON COMMIT DROP')
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO facts VALUES(%s,%s,%s,%s,%s)', rows())
        check(conn, 'postgresql-scoped-table')
    with tempfile.TemporaryDirectory(prefix='postgres-parquet-comparison-') as directory:
        source = Path(directory) / 'source.parquet'
        dataset(source)
        check_parquet(source, 'duckdb-local-parquet')
    print('PASS PostgreSQL/DuckDB table/Parquet semantic parity against a deterministic oracle; timings are observations without adoption thresholds')
