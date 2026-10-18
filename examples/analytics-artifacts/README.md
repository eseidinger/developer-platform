# Application-owned DuckDB/Parquet artifacts

This application example publishes Parquet snapshots in an explicitly bound
RustFS bucket. DuckDB runs inside the application. It requires no shared DuckDB
server or platform API dependency. Install the pinned `requirements.txt` in the
application environment; the platform's optional `analytics-fixtures` group is
only for verification. DuckDB 1.5.6 supports the Python/Parquet APIs used here;
see the [Python documentation](https://duckdb.org/docs/current/clients/python/overview)
and [Parquet documentation](https://duckdb.org/docs/data/parquet).

Bind an S3 resource to the component and use its injected `S3_BUCKET`,
`AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and
`AWS_DEFAULT_REGION`. Readers need read-only grants; publication requires
read-write. Native clients outside the cluster use the documented SSH lease
tunnel. Do not supply an operator key. Restart on automatic credential rotation.

```bash
python artifacts.py publish input.parquet > snapshot-reference.json
python artifacts.py read snapshot-reference.json verified.parquet
```

Run these application commands from `examples/analytics-artifacts` with its
requirements installed and the binding/lease environment configured. Run the
later fixture commands from the repository root.

Publication uses new UUID keys and requires native bucket versioning. The small
reference identifies an exact manifest version, length and SHA-256; that manifest
identifies an exact Parquet version, length and SHA-256. References contain no
credentials. Preserve them with the application's authoritative dataset metadata
and backup. Consumers use the bucket from their binding, stream bounded object
versions, verify both checksums and publish a local file only after verification.
A later write at either key cannot change that reference's result. Corruption,
missing versions, unsupported manifests and invalid size/version fail closed.
Existing local files are never overwritten. This example caps one snapshot at
512 MiB and its manifest at 64 KiB; larger datasets need a bounded multipart
manifest/application implementation.

Query the verified local snapshot using trusted application SQL:

```python
import duckdb
with duckdb.connect(config={"memory_limit": "256MB", "threads": 2,
        "autoinstall_known_extensions": "false", "autoload_known_extensions": "false"}) as conn:
    snapshot = conn.read_parquet("verified.parquet")
    print(snapshot.aggregate("count(*)").fetchall())
```

Do not expose arbitrary SQL, local paths or extension installation to untrusted
callers. Local materialization separates measured transfer/checksum cost from
query-engine cost, uses bounded temporary disk, and avoids requiring DuckDB to
install a remote S3 extension at runtime. Applications own schema/data validation,
dataset manifests, retention, lineage and domain query semantics. This is logical
snapshot immutability, not object lock: an authorized writer can delete retained
versions. Recovery depends on the platform's encrypted bucket/catalog backup and
application reference backup; PostgreSQL remains appropriate for authoritative
metadata and transactional outbox updates. Do not delete the source before
verified publication and a successful metadata transaction.

The opt-in real-provider fixtures compare PostgreSQL tables, DuckDB tables and
local/versioned-S3 Parquet against the same deterministic Python oracle. They
cover daily/monthly aggregation, weather joins, windows and scenario costs using
180 synthetic rows. Timings have no adoption threshold and are not representative
domain benchmarks. S3 checks include new versions at existing keys, corruption
denial and empty-volume restore followed by fresh scoped approval.

```bash
uv sync --project platform/app --group analytics-fixtures --locked
STORE_ANALYTICS_FIXTURE=1 uv run --project platform/app --group analytics-fixtures python scripts/verify-named-postgres.py
STORE_ANALYTICS_FIXTURE=1 uv run --project platform/app --group analytics-fixtures python scripts/verify-rustfs.py
```

Run fixture commands from the repository root with Docker available. They create
and remove uniquely named disposable providers; no live installation is changed.
ODIP's versioned energy datasets, large-volume/storage comparisons, application
metadata integration and deployed off-host recovery remain separate acceptance.
