# Phase 9 — Data Store Measurement and Comparison

Status: planned, unscheduled as of October 18, 2026. This phase owns the
quantitative performance work and comparative experiments previously embedded in
Phases 7 and 8. Existing synthetic fixtures, metric collectors and dashboard
source remain evidence of implementation; they do not close deployed or domain
measurement tasks.

**Task:** [PLAN-037](../backlog.md#data-store-expansion-tasks). The source
provider tasks PLAN-026–033 retain their functional acceptance and existing
evidence; PLAN-037 tracks the moved measurement and comparison exit work.

## Scope and entry

Phase 7 retains functional provisioning, scoped access, lifecycle, capacity
admission, basic health/alerting and backup/purge safeguards for planned stores.
Phase 8 retains the same operational acceptance for any owner-selected deferred
store. Restore, rebuild and application reconnection acceptance belongs to
[Phase 10 package 10.13](phase-10-anytime-leftovers.md#1013-verify-deployed-data-store-recovery-plan-027plan-033-follow-up),
with PostgreSQL restore in package 10.11. Neither provider phase waits for
benchmark scores, comparative results or the eight performance dashboards.
Measuring throughput, latency, resource cost or recovery duration belongs here;
the recovery exercises themselves belong to Phase 10.

Start each measurement package when the corresponding provider or application
fixture is available. Packages can run independently; a deferred Phase 8 store
does not block measurements for a Phase 7 store. ODIP, VEF, Energy and Bot Social
own their domain datasets, relevance judgments and interpretation. The platform
owns common metric collection, dashboard provisioning and bounded operational
measurements. No comparison result or threshold gates store selection or adoption.

## Comparison packages

### 9.1 — Analytics and object storage

- Compare PostgreSQL and DuckDB on the same versioned ODIP energy data: daily and
  monthly aggregation, generation/weather joins, windows, scenario costs and
  increasing volumes. Separate engine time from physical storage and transfer.
- Compare PostgreSQL raw artifacts with immutable, versioned S3/Parquet objects:
  large-object streaming, checksums, versioning, backup/recovery and cost.
- Record data versions, equivalent results, environment and repeatable commands.
  The existing 180-row synthetic fixture is a functional reference, not ODIP
  domain or large-volume measurement acceptance.

### 9.2 — Search

Compare PostgreSQL full-text search and OpenSearch on versioned ODIP metadata and
instructions, with Bot Social posts when available. Use manually judged queries
for ranking, filters, facets, typo handling and incremental updates. Record
latency and quality separately from the provider's functional rebuild tests.

### 9.3 — Graph

Compare relational/recursive PostgreSQL queries, Apache AGE and Neo4j Community
on equivalent VEF transitive dependencies, cycles and change-impact data. Add
Energy, ODIP lineage and Bot Social scenarios when their fixtures exist. Record
semantic equivalence, version/feature coverage and operational cost. VEF retains
constraint evaluation and optimization responsibility.

### 9.4 — Vector retrieval

Compare pgvector and Qdrant, with OpenSearch if selected, on a versioned domain
corpus and embedding model. Measure Recall@k, MRR or nDCG, p95 latency, filtering,
indexing, memory and update/deletion behavior. Separate semantic memory, durable
agent state and conversation history. No relevance threshold gates adoption.

### 9.5 — Deferred-store comparisons

For each owner-activated Phase 8 provider, compare PostgreSQL/TimescaleDB/
ClickHouse time-series and OLAP workloads (DuckDB as a bounded reference), Valkey
against indexed/precomputed PostgreSQL and local application caching, or
MongoDB/CouchDB against PostgreSQL JSONB. Use reproducible loads and include
invalidation, consistency, indexing/schema evolution, memory and operating cost
as applicable. Unactivated providers require no benchmark.

## Eight performance dashboards

**Owner-requested scope (October 17, 2026):** Deliver all eight dashboards below
in Phase 9, after the relevant provider or workload is available. Extend the
existing PostgreSQL dashboard and link every performance dashboard from the
existing named-resource overview. The overview's quota, lifecycle, credential
cleanup and quarantine panels remain the common operational entry point.
All eight performance dashboards now have generated definitions. Native
PostgreSQL/OpenSearch/Qdrant statistics, RustFS OTLP, container measurements and
Community JVM/relay metrics have source/local evidence. The application collector
and real DuckDB profiling example provide workload histograms/numeric fields;
external application instrumentation and deployed collection remain open.
Private collector roles, missing/stale-data handling, alerts and real Prometheus
query validation are implemented. See the [monitoring guide](../../../../infrastructure/monitoring/README.md#phase-7-store-performance).

| Dashboard / package | Required panels | Metrics source and implementation constraints |
|---|---|---|
| **PostgreSQL performance — Phase 9 / PLAN-026** | Transactions/sec and rollbacks; connection usage; blocked sessions and oldest transactions; cache hits and disk I/O; WAL/checkpoints; temporary spills; vacuum activity and dead tuples. | Extend the existing PostgreSQL exporter using native statistics. Optionally add aggregated execution statistics through `pg_stat_statements`, after reviewing preload changes, collection permissions and overhead. Do not export SQL text or unbounded query identifiers. |
| **DuckDB / Parquet analytics — Phase 9 / PLAN-027** | Query duration and CPU time; peak buffer memory; temporary spill usage; rows scanned/returned; artifact transfer/checksum time; bytes downloaded; successful/failed runs. | Instrument application/job operations and extract selected DuckDB profiling fields. DuckDB is embedded: show workload/job observations rather than inventing a shared server. Keep query-engine time separate from storage transfer and integrity verification. |
| **RustFS S3 performance — Phase 9 / PLAN-027** | GET/PUT throughput and latency; transferred bytes; errors/timeouts; backpressure; storage growth; scanner/healing activity; disk pressure. | Verify the pinned release's OTLP metrics and route them through Alloy where compatible, with a bounded metrics pipeline into Prometheus. Current operations documentation describes OTLP export; do not assume a native Prometheus scrape endpoint. Validate availability and scope of each operation/bucket metric before adding panels. |
| **OpenSearch performance — Phase 9 / PLAN-028** | Search/indexing throughput and mean operation time; active searches; thread-pool queues/rejections; JVM heap/GC; circuit breakers; shard health; segment merges; cache efficiency; disk watermarks. | Use a restricted exporter polling cluster/node/index statistics over verified private TLS. Add application histograms for end-to-end search percentiles; accumulated native operation counts/times provide means, not p95/p99. Include single-node topology expectations when interpreting shard health. |
| **Apache AGE performance and projection health — Phase 9 / PLAN-029** | Graph-query throughput/latency/errors; SQL lock waits and spills; projection freshness and pending source updates; rebuild duration/failures; last successful validation. | Reuse PostgreSQL statistics for database behavior, instrument graph operations in applications, and expose projection-worker freshness/rebuild metrics. Identify each signal's source; do not attribute shared PostgreSQL CPU/I/O exclusively to AGE. |
| **Neo4j Community instance performance — Phase 9 / PLAN-029** | Per-resource instance availability/restarts; CPU/memory; JVM heap/GC; disk growth; Bolt connections; instrumented query latency/errors; backup interruption and duration. | Combine container metrics, a standard JVM exporter and client instrumentation, verified against the selected Community image. Validate connection counters against an available source. Native database-internal counters are conditional: the documented built-in metrics exporter is an Enterprise feature. Do not introduce a commercial edition to fill panels. Discover each dedicated instance from its stable resource identity. |
| **pgvector performance — Phase 9 / PLAN-030** | Vector-query throughput/latency; index size and usage; HNSW/IVFFlat build progress; vacuum activity; resource consumption during indexing. | Combine PostgreSQL statistics/index-build progress and application vector-query histograms. Clearly distinguish shared-server usage from attributable workload usage. Recall measurements come only from explicit, versioned comparison runs, not an inferred live operational metric. |
| **Qdrant performance — Phase 9 / PLAN-030** | Search/upsert throughput; latency percentiles and errors; point/vector counts; indexed versus unindexed points; optimizer activity; memory/page faults; file descriptors; snapshots. | Privately scrape native `/metrics`, with bounded per-collection dimensions and selected telemetry fields where required. Verify histogram and collection coverage in the pinned release; do not assume cloud-only `/sys_metrics` is available. |

### Common collection and dashboard requirements

- Keep dashboards, collectors, recording rules and alerts in versioned source and
  provision through the existing Grafana/Prometheus/Alloy and Compose/Ansible
  workflow. Extend the dashboard generator rather than hand-editing generated
  JSON. Start with PostgreSQL enhancements and RustFS/OpenSearch/Qdrant native
  collection, then AGE/pgvector workload views and DuckDB analytics; deliver
  Neo4j coverage with its dedicated-instance provider. All eight remain in scope.
- Filter by provider, project, stable resource ID and instance where reliable
  attribution exists. Clearly label shared-service signals. Use catalog mappings
  for generated database/bucket/index/collection names; dashboard filters are not
  an authorization boundary. Apply the platform's monitoring access policy.
- Show native performance alongside container CPU, memory limits, restarts and
  disk pressure. Add missing Docker-container collection where needed; existing
  Kubernetes workload metrics do not cover these Compose stores. Measure
  collector overhead and account for it in single-host capacity admission.
- Use bounded operation labels and histograms where percentiles are needed.
  Exclude raw queries, object keys, document contents, credentials and arbitrary
  client labels. Collect only reviewed numeric DuckDB/profile fields; do not
  ship complete query plans or profiling payloads into telemetry. Bound scrape
  frequency/timeouts, sample counts, label cardinality and payload sizes.
- Keep metrics/admin endpoints private. Use restricted monitoring identities
  where supported, store collector secrets privately and verify TLS. Document
  edition/API limitations and exact required permissions; monitoring must not
  widen human/application grants or expose administrator keys to browsers.
- Show collector health, collection errors, last successful collection and stale
  or missing data explicitly. Distinguish unavailable, disabled/unselected,
  idle and scheduled maintenance; missing series must not imply healthy or zero.
- Add actionable alerts for unavailability, sustained errors/rejections, resource
  exhaustion and stalled maintenance. Tune thresholds using observed workloads;
  dashboard thresholds do not impose store-adoption or benchmark success criteria.
  Link relevant backup status, resource lifecycle and operator runbooks.

### Verification and evidence

For each pinned image/extension and dashboard, record which panels use native,
container, collector or application signals. Verify actual metric names, types,
units, permissions and dimensions in disposable fixtures before generating
queries. Unsupported internal signals require a documented alternative or
visible capability limitation; do not supply fabricated values or permanently
empty panels. Use histogram buckets for quantiles and counter rates for means;
do not reinterpret averages as percentiles.

Exercise representative queries/writes and indexing/rebuild/analytics work;
verify throughput, error and latency signals change as expected. Test missing
collectors, provider outages, counter resets, stale data and collection-denied
credentials, plus alert firing/resolution and bounded labels. Verify dashboard
provisioning, queries and drill-down links locally, then record deployed
collection/visualization separately. Neo4j fixtures must cover per-instance
identity/discovery and scheduled offline backup visibility. External applications
own their required workload instrumentation; local synthetic evidence does not
claim external instrumentation or deployed acceptance.

Reference interfaces: [PostgreSQL statistics](https://www.postgresql.org/docs/18/monitoring-stats.html),
[pgvector monitoring](https://github.com/pgvector/pgvector#monitoring),
[DuckDB profiling metrics](https://duckdb.org/docs/current/dev/metrics),
[RustFS observability](https://docs.rustfs.com/en/operations/observability),
[OpenSearch node statistics](https://docs.opensearch.org/latest/api-reference/nodes-apis/nodes-stats/),
[Qdrant monitoring](https://qdrant.tech/documentation/ops-monitoring/monitoring/) and
[Neo4j metrics export](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/expose/).
These references guide release-specific verification rather than guaranteeing
that every current-documentation metric exists in the pinned images.

## Exit

Record each performed comparison with versioned data, workload, environment,
commands, equivalent-result checks, measurements, owner interpretation and limits.
For each of the eight dashboards, record actual metric names/types/units,
permissions, query validation, deployed collection and visualization, missing or
stale-data behavior and alert response. Mark unavailable external application
instrumentation and unscheduled comparisons explicitly; do not claim them passed.
Phase 9 completion is independent of Phase 7/8 provider acceptance and of Phase 10
leftovers.
