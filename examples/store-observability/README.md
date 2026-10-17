# Store workload metrics

Copy `metrics.py` into an application that needs the AGE, pgvector, Neo4j or
DuckDB workload panels. It uses only the Python standard library and opens no
listener. Return `StoreMetrics.exposition()` from the application's existing
protected metrics route and enable the platform's normal application metrics
opt-in. The platform supplies the project/application/component scrape labels;
this helper supplies only stable resource UUID, provider and reviewed operation
labels. A dashboard filter is not an access-control boundary.

```python
from metrics import StoreMetrics

metrics = StoreMetrics(resource_id, "pgvector")
with metrics.operation("search"):
    results = run_vector_search()

# In the application's existing metrics handler:
body = metrics.exposition()
```

Use separate instances for different resources and workload providers. Supported
providers/operations are fixed in `OPERATIONS`; arbitrary query text, user names,
object keys and request IDs are rejected as operation labels. Observations are
in-memory per process, so counters reset on restart. Include the scrape instance
when inspecting replicas; sum histogram buckets before computing percentiles.
Finite latency buckets extend to 300 seconds. Respect the application scrape's
series/body limits when instrumenting several resources.

For an AGE projection worker, time `rebuild` and `validate` operations and publish
numeric `projection_lag_seconds`, `pending_updates` and
`last_validation_timestamp_seconds` from the protected authoritative source and
its actual validation result. Do not infer freshness from a successful SQL
connection. Graph/vector latency measures the instrumented client operation,
separately from shared PostgreSQL server CPU, locks and I/O.

For DuckDB, call `duckdb_profile(profile_json)` after a profiled query. It selects
only CPU time, peak buffer memory, temporary spill size and scanned/returned row
counts. Full profiles contain SQL, paths and operator trees: keep them private
and do not publish them as telemetry. Profile gauges describe the last observation,
not cumulative counters. Instrument `transfer`, `checksum` and `publish`
separately from `query`; `transfer_bytes` is the last transfer's measured size.
Embedded jobs can use a stable dataset/job UUID without provisioning a shared
DuckDB service or S3 bucket. Publish a final metrics observation through the
application's existing job-monitoring mechanism before a short-lived job exits.

Run the real DuckDB profiling check with the optional fixture dependency:

```bash
uv run --project platform/app --group analytics-fixtures python examples/store-observability/verify.py
```

The helper provides instrumentation, not automatic coverage of external
applications. Register each consuming application's metrics endpoint and verify
its workload panels after integration. See the
[store monitoring workflow](../../infrastructure/monitoring/README.md#phase-7-store-performance)
and the [Phase 7 plan](../../docs/maintainers/delivery/plans/phase-7-planned-data-stores.md#native-performance-dashboards).
