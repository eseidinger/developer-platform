# Capacity and store monitoring

See the [monitoring directory guide](README.md) for configuration ownership and
related contracts. Run commands from the repository root.

## Workload CPU and memory capacity

**Workloads and capacity** has a project-namespace selector and pod/deployment
comparisons of CPU usage (cores), memory working set (bytes), configured
requests, and configured limits. CPU usage needs at least two scrapes in its
five-minute rate window. Deployment totals join Pod → ReplicaSet → Deployment
ownership, so rolling ReplicaSets are grouped together; scheduled jobs remain
visible as pods. Only Pending, Running and Unknown pods contribute to current
resource totals. Historical samples remain available over the selected time
range.

Requests and limits are steady-state container sums, including native
restartable init sidecars (`restartPolicy: Always`). Ordinary sequential init
containers and pod overhead are excluded: these panels do not claim the
scheduler's effective peak startup requirement. A limit is omitted when any
contributing container or deployment pod lacks a positive limit; missing limits
never mean zero capacity. Host panels continue to show the whole host,
independently of namespace selection.

Prometheus discovers all nodes through the TLS-verified Kubernetes API and
scrapes private kubelet HTTPS `/metrics/cadvisor` endpoints using a separate
`capacity-metrics-reader` service account. It can list/watch nodes and get
`nodes/metrics`; it cannot proxy nodes, exec, read secrets or mutate workloads.
The cluster CA verifies both discovery and kubelet serving certificates.
Bootstrap extracts `.runtime/capacity-reader.token` and
`.runtime/capacity-reader-ca.crt`, mounting them only into Prometheus; the token
has the existing UID 65534 read ACL. Revoke by deleting
`capacity-metrics-reader-token` and rebootstrap to reissue it.

Only `container_cpu_usage_seconds_total` and
`container_memory_working_set_bytes` for named project containers are retained;
sandbox containers and arbitrary labels are discarded. Scrapes are bounded to
10,000 retained samples and a 16 MB response per node. The **Container usage
collection** panel and existing scrape alerts expose collection failures;
missing usage is not synthesized as healthy zero. Recording rules in
`capacity-rules.yaml` combine these metrics with kube-state-metrics resource and
ownership data.

`scripts/tests/components/observability/check-monitoring.py` validates the
configuration and executes `tests/capacity.test.yaml`: it covers namespace
isolation, rolling ReplicaSets, sidecars, ordinary init exclusion, completed
jobs, and incomplete limits.

## PostgreSQL and host storage

The operator-only **PostgreSQL** dashboard selects one database for connections,
transactions/rollbacks, size, cache hits, temporary files, deadlocks, locks and
oldest transactions. Shared connection usage/limit, uptime and collection health
are explicitly server-wide and independent of the database selector. A database
limit of `-1` means no separate limit and is not plotted as zero capacity. Idle
databases can have no cache-hit ratio until block activity occurs.

`postgres-exporter` is pinned to v0.20.1, has no published host port, and runs
read-only with all capabilities dropped, 128 MiB memory and 0.25 CPU limits.
Prometheus keeps only reviewed aggregate metrics and database/state/lock-mode
labels, with a 5,000-sample, 2 MB scrape budget. Table, user, application-name,
query-text, query-ID and replication-client collectors are disabled. The fixed
`postgres-queries.yaml` aggregates connection states, lock waits and transaction
ages in SQL before export, avoiding collisions and sensitive session labels from
the stock activity collector. It uses the pinned exporter's deprecated custom
query option; revalidate compatibility before upgrading. The shared exporter has
no per-table labels. The Phase 7 collector below adds aggregate named-database
vacuum/dead-tuple observations.

Bootstrap runs `scripts/setup/setup-postgres-monitoring.py` after PostgreSQL is
healthy. It reconciles `platform_monitor` with `pg_monitor`, five connections
maximum, read-only default transactions and a five-second statement timeout. It
receives no application-table grants, superuser, role/database creation,
replication or RLS bypass privileges. The shared exporter connects to `platform`
for catalog statistics. The additional Phase 7 collector receives CONNECT to
retained named PostgreSQL databases for aggregate statistics; neither collector
uses application credentials or table-data grants. `pg_monitor` is a trusted
operator role able to read cluster statistics; never expose its credential to
projects or AI tools.

Run `python3 scripts/init.py` to generate `POSTGRES_MONITOR_PASSWORD` in `.env`,
including on an existing installation. Setup writes
`.runtime/postgres-monitor.password` with a UID 65534 read ACL, mounted only
into the exporter; the password is neither a Compose environment variable nor a
DSN argument. `.env` remains part of the existing protected configuration
backup; the runtime file is regenerated. To rotate, replace the configured
secret, rerun setup and recreate only `postgres-exporter`. To revoke, disable
the `platform_monitor` login and stop the exporter. The private Docker
connection uses the existing PostgreSQL transport (`sslmode=disable`); it adds
no public PostgreSQL or exporter route.

**Workloads and capacity** also displays host disk-space utilization, total and
available bytes, and inode utilization. These panels use node exporter, exclude
virtual filesystems, and are independent of project selection. Space utilization
uses capacity minus space available to an unprivileged process, including
reserved blocks. Filesystems without inode capacity have no inode ratio.

`scripts/tests/components/observability/check-postgres-monitoring.py` creates
disposable PostgreSQL 18, exporter and Prometheus containers. It verifies
repeatable role setup, denied application reads/writes, aggregate privacy,
database selection, absent/unlimited values and dashboard query readback using
production collectors, SQL and metric filters. It pauses the exporter to verify
`up=0`, then resumes it and verifies `pg_up=1`.

## Named-store performance

The named-resource overview links to PostgreSQL, RustFS S3, Apache AGE,
pgvector, and application-owned DuckDB/Parquet dashboards. Regenerate reviewed
definitions with `python3 scripts/generate/generate-dashboards.py`.

The PostgreSQL native collector connects read-only as `platform_monitor` to
named databases, at most eight per pass. It publishes aggregate table, vacuum,
vector-index, and index-build statistics without SQL, user, or index-name labels.
Last-good values keep their original timestamps after a failure; collection
health is separate. The PostgreSQL dashboard also displays shared WAL and
checkpoint statistics.

RustFS 1.0.2 exports S3 metrics over OTLP/HTTP to Alloy's private port 4320. The
allowlist removes unreviewed dimensions before Prometheus export. Object keys,
paths, logs, and trace payloads are excluded from the metrics pipeline. Alloy's
memory limiter uses a 192 MiB hard and 144 MiB soft process-heap budget within
its 256 MiB light-load container limit; the limit covers the entire collector.

Application query latency and DuckDB job profiles require explicit application
instrumentation. The
[collector example and integration guide](../../examples/store-observability/README.md)
opens no listener and returns bounded Prometheus text for an application's
protected metrics route. Missing observations mean unknown, not zero traffic.

Run `scripts/tests/components/observability/verify-store-metric-pipeline.py` for
signed RustFS I/O through production Alloy into disposable Prometheus, sensitive
dimension exclusion, and dashboard query parsing. Alert fixtures include
`tests/native-stores.test.yaml`. PostgreSQL round-robin sampling is bounded;
never-sampled and failed resources remain explicit in health and freshness.
