# Phase 7 — Planned Data Stores

Status: implementation in progress as of October 17, 2026. PostgreSQL named
resources/private access/console are implemented in source with disposable local
evidence; deployed integration/recovery acceptance remains open in package 7.1.
Additional shared-store providers have no operational acceptance recorded here.

The owner requested continued implementation as far as possible with regular
commits. Source/local provider work continues while deployed acceptance remains
open; this does not accept the earlier package's deployed gate or enable a service.
Native RustFS, OpenSearch and Qdrant adapters now pass real isolation, credential,
query and empty-volume recovery fixtures. Opt-in pinned Compose services,
configuration/capacity-gated provider registration and non-demo OpenSearch TLS
initialization are implemented. The actual production Compose definitions pass
disposable health/administration checks. RustFS, Qdrant and OpenSearch Dashboards
native browser login, RO/RW isolation and active-session expiry/revocation now
pass local TLS fixtures. OpenSearch resource workspaces survive human renewal
and are included in usage, backup/recovery and isolated purge. Combined deployed
acceptance remains open; PostgreSQL is the default selection.
See the [RustFS](../../../../persistence/compatibility/rustfs-2026-10-17.md),
[OpenSearch](../../../../persistence/compatibility/opensearch-2026-10-17.md) and
[Qdrant](../../../../persistence/compatibility/qdrant-2026-10-17.md) records.

## Implementation checkpoint — October 17, 2026

Source work has started in `app.stores`: independent resource/grant/credential
catalog, versioned administration requests, API authorization boundaries,
PostgreSQL role/database provisioning and lifecycle/workload reconciliation.
The routes and workers are now wired into the source application. The portal
and CLI manage named resources, grants/bindings and human credential leases;
the private relay enforces credential identity and session deadlines. Browser
consoles and the three opt-in providers have local evidence; deployed acceptance
and external domain comparisons remain in progress. See the
[operator workflow](../../../operators/data-stores.md). Eight API
boundary tests and a disposable real PostgreSQL fixture pass resource isolation,
cross-writer schema ownership, future-object read access, read-only denials,
expiry, session revocation, 30-day worker rotation/retry/deadline handling, real
relay authentication/session expiry and isolated purge. The pinned AGE/pgvector runtime image also passes writer/reader graph/vector
queries and denial of graph writes/extension removal. A disposable real
Keycloak → pgAdmin fixture passes SSO, scoped connection/query, password-saving
denial, expired reconnect and anonymous denial. Production console network/TLS
and deployed access acceptance remain open. The backend suite ran
531 tests successfully (16 skipped); the portal suite passes 46 tests. Production
image construction passes, including bundled RustFS assets and exclusion of the
optional DuckDB dependency from the API runtime. The relay and portal tests cover expiry, denial,
explicit issuance and secret-cache exclusion. No live resources were changed.
Source now includes bounded usage measurements/alerts, the named-store dashboard,
restore quarantine, and version-pinned purge acknowledgment after verified
backup upload/readback. A real encrypted local restic intent fixture passes
purge gating and latest-tombstone replay after an older-state simulation; recovery
requires fresh explicit approval. The fixture additionally restores the real encrypted
SQL/catalog backup into an empty second disposable server, replays purge intent,
rebuilds graphs, retains SQL/vector/outbox data and verifies old-key denial/fresh
read-only approval. This is local evidence, not deployed off-host RPO/RTO acceptance.
The [upgrade runbook](../../../operators/runbooks/store-upgrades.md) covers pinned
release checks, verified pre-upgrade backups, extension upgrades and recovery limits.
AGE authoritative rebuild is implemented and passes a real logical-restore
fixture with two graphs, five labels, a cycle, source-defined indexes and preserved
SQL/pgvector data. See the [dated evidence](../../../../persistence/compatibility/projection-rebuild-2026-10-17.md).
Deployed rebuild/reconnection and recovery timing remain open.
Retirement previews include named resource/grant versions; access fencing commits before namespace deletion. The PostgreSQL reference covers JSONB, full-text search, recursive CTEs, partitions, materialized views and transactional outbox rollback in the real database fixture.
PLAN-026/036 and Phase 7 acceptance remain open.

## Goal and scope

Provide the planned analytical, object-storage, search, graph and vector
capabilities through measured comparisons and optional generic resource providers.
DuckDB/Parquet and one S3-compatible store form the analytical foundation;
OpenSearch, Apache AGE/Neo4j and pgvector/Qdrant follow as targeted experiments.
Stores may be selected at will under the [selection decision](data-store-expansion.md#store-selection-decision).
Comparisons are for learning and do not impose adoption success criteria.

**Entry:** existing PostgreSQL platform capabilities and agreed cross-project
integration contract. Complete package 7.1 before introducing additional stores;
then follow analytics/object storage → search → graph → vector package order,
subject to each package's fixtures. Phase 5 AI operations does not depend on
vector retrieval. Optional Phase 6 and unrelated Phase 9 leftovers do not gate
this work.

**Service placement:** Shared stores run persistently in Docker Compose outside
Kubernetes, alongside PostgreSQL, using the existing operator Compose/Ansible
workflow. Applications remain Kubernetes workloads and access private endpoints
through explicit bindings, managed secrets and network policies. This does not
activate the optional Docker compute adapter. See the
[placement decision](data-store-expansion.md#shared-service-placement-decision).

**Ownership and evidence:** [common acceptance and responsibilities](data-store-expansion.md#ownership-and-common-acceptance)
apply to every package. Track PLAN-026–030 and PLAN-036 in the
[backlog](../backlog.md#data-store-expansion-tasks); external projects retain
benchmarks, adapters and domain assertions.

## Native performance dashboards

**Owner-requested scope (October 17, 2026):** Deliver all eight dashboards below
within Phase 7, alongside the provider/workload packages indicated. Extend the
existing PostgreSQL dashboard and link every performance dashboard from the
existing named-resource overview. The overview's quota, lifecycle, credential
cleanup and quarantine panels remain the common operational entry point.
Native performance coverage below is planned; the existing overview and
PostgreSQL panels do not establish completion of these additions.

| Dashboard / package | Required panels | Metrics source and implementation constraints |
|---|---|---|
| **PostgreSQL performance — 7.1 / PLAN-026** | Transactions/sec and rollbacks; connection usage; blocked sessions and oldest transactions; cache hits and disk I/O; WAL/checkpoints; temporary spills; vacuum activity and dead tuples. | Extend the existing PostgreSQL exporter using native statistics. Optionally add aggregated execution statistics through `pg_stat_statements`, after reviewing preload changes, collection permissions and overhead. Do not export SQL text or unbounded query identifiers. |
| **DuckDB / Parquet analytics — 7.2 / PLAN-027** | Query duration and CPU time; peak buffer memory; temporary spill usage; rows scanned/returned; artifact transfer/checksum time; bytes downloaded; successful/failed runs. | Instrument application/job operations and extract selected DuckDB profiling fields. DuckDB is embedded: show workload/job observations rather than inventing a shared server. Keep query-engine time separate from storage transfer and integrity verification. |
| **RustFS S3 performance — 7.2 / PLAN-027** | GET/PUT throughput and latency; transferred bytes; errors/timeouts; backpressure; storage growth; scanner/healing activity; disk pressure. | Verify the pinned release's OTLP metrics and route them through Alloy where compatible, with a bounded metrics pipeline into Prometheus. Current operations documentation describes OTLP export; do not assume a native Prometheus scrape endpoint. Validate availability and scope of each operation/bucket metric before adding panels. |
| **OpenSearch performance — 7.3 / PLAN-028** | Search/indexing throughput and mean operation time; active searches; thread-pool queues/rejections; JVM heap/GC; circuit breakers; shard health; segment merges; cache efficiency; disk watermarks. | Use a restricted exporter polling cluster/node/index statistics over verified private TLS. Add application histograms for end-to-end search percentiles; accumulated native operation counts/times provide means, not p95/p99. Include single-node topology expectations when interpreting shard health. |
| **Apache AGE performance and projection health — 7.4 / PLAN-029** | Graph-query throughput/latency/errors; SQL lock waits and spills; projection freshness and pending source updates; rebuild duration/failures; last successful validation. | Reuse PostgreSQL statistics for database behavior, instrument graph operations in applications, and expose projection-worker freshness/rebuild metrics. Identify each signal's source; do not attribute shared PostgreSQL CPU/I/O exclusively to AGE. |
| **Neo4j Community instance performance — 7.4 / PLAN-029** | Per-resource instance availability/restarts; CPU/memory; JVM heap/GC; disk growth; Bolt connections; instrumented query latency/errors; backup interruption and duration. | Combine container metrics, a standard JVM exporter and client instrumentation, verified against the selected Community image. Validate connection counters against an available source. Native database-internal counters are conditional: the documented built-in metrics exporter is an Enterprise feature. Do not introduce a commercial edition to fill panels. Discover each dedicated instance from its stable resource identity. |
| **pgvector performance — 7.5 / PLAN-030** | Vector-query throughput/latency; index size and usage; HNSW/IVFFlat build progress; vacuum activity; resource consumption during indexing. | Combine PostgreSQL statistics/index-build progress and application vector-query histograms. Clearly distinguish shared-server usage from attributable workload usage. Recall measurements come only from explicit, versioned comparison runs, not an inferred live operational metric. |
| **Qdrant performance — 7.5 / PLAN-030** | Search/upsert throughput; latency percentiles and errors; point/vector counts; indexed versus unindexed points; optimizer activity; memory/page faults; file descriptors; snapshots. | Privately scrape native `/metrics`, with bounded per-collection dimensions and selected telemetry fields where required. Verify histogram and collection coverage in the pinned release; do not assume cloud-only `/sys_metrics` is available. |

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

## Ordered work packages

### 7.1 — PostgreSQL Baseline and Integration

**Tasks:** PLAN-026 and PLAN-036 (human access paths). **Source:** phase 0. **Entry:** existing PostgreSQL platform
capabilities and agreed external integration contract.

- Extend PostgreSQL native performance monitoring and establish the common collector/dashboard verification workflow; apply the
  [native performance dashboard requirements](#native-performance-dashboards).

- Enforce the [resource administration policy](data-store-expansion.md#resource-administration-decision):
  project admins manage their own resources, grants and bindings; platform admins
  have those capabilities across all projects. Preserve cross-project approval,
  purge prerequisites/confirmation and audit trails. Native/console data access
  still requires explicit human grants; verify role boundaries and no implicit
  data access from administrative status.
- Implement the [independent project-resource and binding contract](data-store-expansion.md#resource-lifecycle-and-binding-decision)
  for PostgreSQL first: separate named-resource lifecycle, multiple resources per
  project, explicit application/component bindings, scoped credentials/permissions,
  rotation/revocation and independent retention. Verify unbound/foreign component
  denial, binding removal and explicit permanent deletion behavior.
- Apply the [quota exhaustion policy](data-store-expansion.md#storage-quota-exhaustion-decision):
  block storage growth at quota where supported, preserve reads/authorized cleanup
  and alert administrators. Require explicit capacity-checked approval for quota
  increases; verify unaffected-resource isolation and document provider limits,
  including admission/monitoring substitutes where hard quotas are unavailable.
- Implement [owner-approved cross-project resource bindings](data-store-expansion.md#cross-project-resource-sharing-decision):
  consumer-project administrators request access for a named application/component,
  resource-owning project administrators approve its explicit mode, and the platform
  provisions scoped access. Add API/CLI/portal approval/rejection/revocation and
  verify pending denial, scope changes, active-session cleanup and ownership retention.
- Implement the [retention-first lifecycle](data-store-expansion.md#deletion-and-retirement-decision):
  application/binding removal revokes only its consumer access; resource/project
  retirement revokes all affected access and retains data; separate confirmed
  purge requires retirement and completed cleanup. Verify retries, partial cleanup,
  stale confirmation, unaffected consumers and backup-retention/recovery semantics.
- Implement [automatic application credential rotation](data-store-expansion.md#application-credential-rotation-decision)
  every 30 days, with managed-secret updates and controlled restarts of bound
  components.
  Applications must tolerate restart; verify readiness and new-credential access
  before promptly retiring the old generation, with at most one hour of overlap. Cover interrupted rotation,
  partial rollouts and revocation across generations without affecting unrelated
  bindings or restarting shared stores. Verify rotation scheduling across controller
  restarts; revoke old credentials and close their connections by the one-hour
  deadline even on failed rollout, reporting recovery needs without extending
  overlap on retries.
- Extend [human access to named resources](data-store-expansion.md#human-access-to-named-resources)
  with explicit read-only/read-write modes, separate resource-scoped human
  credentials and private connection paths. Add API/CLI/portal grant management,
  permission changes, rotation/expiry and revocation. Human credentials must
  [expire and renew against the current active grant](data-store-expansion.md#human-credential-expiry-decision);
  use a 24-hour default credential validity and close active connections at
  credential expiry through private and console access. Require renewal and
  reconnection; renewal must not extend old sessions. Early renewal preserves
  the old credential and its connections until their original expiry while
  issuing a new credential with its own validity. Revocation, retirement and
  permission changes apply across all outstanding credential generations.
  Verify PostgreSQL data-write
  and application-schema DDL permissions for human/application writers, without
  server/global escalation; cover two resources with different grants,
  future objects, cross-resource/project denial and active-session downgrade.
  Permit startup migrations through read-write bindings; a dedicated migration
  identity/job is optional. Verify cross-writer object ownership and removal of
  schema authority on downgrade/revocation. Apply this grant model to each
  subsequently introduced provider.
- Deliver [both private and browser-console access](data-store-expansion.md#private-and-browser-console-access-decision)
  (`PLAN-036`): resource-aware SSH/native-client access and a portal-launched
  authenticated pgAdmin console using each human's scoped resource identity.
  Extend both paths with each selected provider, including its console adapter.
  Verify backend enforcement and revocation/downgrade of existing sessions; raw
  store ports remain private and consoles never receive shared admin credentials.
- Establish [operator-triggered shared-store upgrades](data-store-expansion.md#shared-store-upgrade-decision)
  with pinned images/extensions/consoles, a verified recoverable backup,
  release-specific compatibility checks and a fixture-validated recovery procedure.
  Applications must tolerate maintenance interruption and reconnect/restart.
  Verify data, scoped access and platform integrations afterward; do not assume
  an older image can read migrated data. Keep automatic credential rotation
  independent while preserving its overlap deadline during maintenance.
- Use the owner-accepted clean setup: update and recreate application/resource
  declarations against the new contract. Legacy implicit database provisioning,
  automatic access for every component and compatibility/migration paths are not
  requirements. Record reset steps and impacts before performing recreation.
- Complete ODIP → VEF deployment acceptance for Energy, linking the generic
  platform evidence and external domain assertions in the
  [energy-system integration plan](energy-system-integration.md).
- Exercise PostgreSQL provisioning and recovery; document JSONB, full-text search,
  recursive CTEs, materialized views, partitioning, and transactional-outbox baselines.
- Reuse existing Phase 9 evidence and record newly performed integration/recovery
  checks against their original tasks; do not close unrelated leftovers.

**Exit:** the independent resource/binding contract passes PostgreSQL lifecycle,
isolation, named-resource human read-only/read-write access through both private
and browser-console paths, and recovery
acceptance; a versioned cross-project acceptance record
and reproducible PostgreSQL reference establish the gate for additional stores. Local-only
integration or the imported roadmap's starting-point claims do not satisfy it.

**Extension compatibility evidence (October 17, 2026):** PostgreSQL 18.6 with
pgvector 0.8.7, AGE 1.8.0 and deferred TimescaleDB 2.30.2 passed the 16-case local
coexistence/query matrix and restart checks. See the
[version pins, results and limitations](data-store-expansion.md#postgresql-extension-compatibility-check).
AGE-only and combined logical restores reproduced stale graph OIDs; the tested
fixture-only repair is not full recovery acceptance. Implement explicit per-resource
extension selection, safe AGE session/preload configuration and verified AGE
recovery/rebuild as part of PLAN-026/029. Live services remain unchanged.

### 7.2 — Analytics and S3-Compatible Object Storage

**Task:** PLAN-027. **Source:** phase 1. **Entry:** package 7.1 integration acceptance.

**Source/local increment (October 17):** The
[application artifact example](../../../../examples/analytics-artifacts/README.md)
publishes exact-version, checksum-verified Parquet snapshots in a bound RustFS
bucket and verifies them before DuckDB reads local data. Its manifest/reference
contract survives later writes at the same keys and empty-volume restore with
fresh scoped approval. Opt-in fixtures compare scoped PostgreSQL tables, DuckDB
tables and local/versioned-S3 Parquet against a deterministic Python oracle for
daily/monthly aggregation, weather joins, windows and scenario costs. Engine
timings and transfer/checksum cost are separate observations without adoption
thresholds. DuckDB is confined to applications and the optional fixture group.
The 180-row synthetic fixture is not ODIP domain/large-volume acceptance; application
metadata/outbox integration and deployed recovery remain open.

- Deliver the RustFS S3 and DuckDB/Parquet analytics performance dashboards, including native OTLP and application/job collection; apply the
  [native performance dashboard requirements](#native-performance-dashboards).

- ODIP compares PostgreSQL and DuckDB on the same versioned energy data:
  daily/monthly aggregation, generation/weather joins, windows, scenario costs,
  and increasing data volumes. Separate query-engine and physical-storage effects.
- Compare PostgreSQL raw artifacts with immutable, versioned S3/Parquet artifacts:
  large-object streaming, checksums, versioning, backup/recovery, and cost.
- Implement owner-selected [RustFS](data-store-expansion.md#object-storage-selection-priority)
  as a shared, continuously running Docker Compose service with its official
  browser console and private native S3 access. Pin verified compatible releases;
  verify scoped console login, 24-hour human credential/session expiry and
  automatic application rotation every 30 days with at most one-hour overlap.
  Preserve the priority of straightforward single-host operation: reproducible
  setup, required S3 behavior, isolation/bindings, measured resource use, upgrades
  and encrypted off-host backup/recovery. Future distributed deployment is not
  an initial requirement. Add a generic S3-compatible resource provider backed by
  RustFS with named project buckets, explicit component bindings, scoped
  credentials/policies, limits and lifecycle/recovery coverage under the common
  acceptance. Product selection is resolved; deployment and acceptance are open.
  DuckDB is an application analytical engine, not necessarily a shared service.

**Exit:** ODIP publishes and consumes versioned datasets independently of physical
storage, the analytical comparison is reproducible, and the selected object-store
provider passes provisioning and recovery acceptance.

### 7.3 — Full-Text Search

**Source/local checkpoint (October 17, 2026):** The exact-index OpenSearch
provider and official pinned Dashboards are implemented. Real-browser fixtures
pass native login, Discover, read-only/read-write data and mapping permissions,
foreign-resource denial, workspace isolation and renewal, and already-open
session expiry/revocation. Resource-scoped saved views are editable in both
modes; read-only document/schema access remains enforced natively. Native
fixtures pass empty-volume restoration with fresh scoped approval and isolated
workspace/data purge. These are synthetic local checks; judged domain search
comparisons, application rebuild semantics and deployed acceptance remain open.
See the [compatibility evidence](../../../../persistence/compatibility/opensearch-2026-10-17.md).

**Task:** PLAN-028. **Source:** phase 2. **Entry:** package 7.2 analytical foundation.

- Deliver the OpenSearch native performance dashboard and restricted statistics collection; apply the
  [native performance dashboard requirements](#native-performance-dashboards).

- ODIP compares PostgreSQL FTS and OpenSearch using shared dataset descriptions,
  metadata and documentation; Bot Social posts can follow when available.
- Evaluate ranking, filters, facets, typo handling, incremental updates and latency
  against manually judged queries. Keep hybrid retrieval as a later extension.
- When selected, expose an optional OpenSearch provider; verify index rebuilds and
  source-of-truth/update semantics while PostgreSQL remains authoritative.

**Exit:** document any judged search-quality observations and the selected
provider; any introduced provider meets common lifecycle acceptance. Search
quality or benchmark results do not gate selection.

### 7.4 — Graph Data

**Task:** PLAN-029. **Source:** phase 3. **Entry:** package 7.3 foundation and
versioned VEF dependency fixtures; Bot Social experiments additionally require Core.

**Implementation constraint verified October 17, 2026:** The current Neo4j
[edition comparison](https://neo4j.com/docs/cypher-manual/25/introduction/cypher-neo4j/)
limits Community Edition to one user database and gives every user full access.
It therefore cannot satisfy the original shared-instance isolation and independent
read-only/read-write grant contract.

**Owner-selected integration decision (October 17, 2026):** Use a dedicated
Community Docker instance and persistent volume per named Neo4j resource,
initially one resource per project, shared through explicit component bindings.
Keep provisioned instances running until retirement. Advertise full instance
access only and reject unsupported read-only grants; this is an explicit
Neo4j-specific placement/access exception. Implement private native access and
Neo4j Browser, separate human/application identities, existing expiry/rotation
and active-session fencing, per-instance capacity/monitoring, offline backup
interruptions and verified recovery/purge. Verify native full-access capabilities
cannot bypass platform identity or lease controls. No Docker socket in the API
or commercial edition is selected. Keep the provider unavailable until these
fixtures pass. See the [complete decision](data-store-expansion.md#neo4j-community-dedicated-instance-decision).

- Deliver AGE graph/projection monitoring and the Neo4j Community per-instance performance dashboard with the dedicated-instance provider; apply the
  [native performance dashboard requirements](#native-performance-dashboards).

- Compare relational PostgreSQL/recursive CTEs, Apache AGE, and Neo4j Community
  Edition for transitive dependencies, cycles, and change-impact analysis in VEF.
- Extend to Energy compatibility, ODIP lineage, and Bot Social two-to-four-hop
  relationships, mutual contacts and recommendations as external fixtures permit.
- Resolve the recorded [AGE logical-restore limitation](data-store-expansion.md#apache-age-restore-diagnosis)
  through the owner-selected [rebuildable-projection policy](data-store-expansion.md#apache-age-rebuild-policy):
  protect authoritative sources, graph definitions and loaders, and recreate AGE
  graphs from those sources within the selected recovery targets. AGE must not
  hold the sole copy of unique domain data; durable human/application graph edits
  must be represented in protected sources/definitions. Check Cypher behavior and data,
  multiple graphs/labels, ownership/permissions and application reconnection;
  successful `pg_restore` alone is insufficient. Preserve non-superuser
  application roles with explicit AGE session/preload configuration.
- Check extension/version compatibility and feature coverage. Provide optional
  AGE or Neo4j support when selected, with common operational acceptance.

**Exit:** equivalent graph semantics and measured operational tradeoffs are
recorded, with rebuild/recovery evidence for introduced providers. VEF retains
constraint evaluation and optimization responsibility.

### 7.5 — Vector Retrieval and AI Memory

**Task:** PLAN-030. **Source:** phase 4. **Entry:** versioned retrieval fixtures,
selected AI/RAG experiment and the available platform foundation. Phase 5 operations assistance
does not require this package.

- Deliver pgvector and Qdrant performance dashboards, including bounded collection metrics and instrumented vector-query latency; apply the
  [native performance dashboard requirements](#native-performance-dashboards).

- Compare pgvector and Qdrant; include OpenSearch if already introduced. Use ODIP
  dataset discovery, Bot Social topic similarity, Energy documentation, or platform
  knowledge collections with explicit relevance judgments.
- Measure Recall@k, MRR or nDCG, p95 latency, filtering, indexing time, memory,
  and update/deletion behavior. Record embedding model and dataset versions.
- Separate semantic memory, durable agent state, and conversation history. Add
  optional extension/provider support when selected; retrieval results do not gate adoption.

**Exit:** reproducible retrieval-quality results and a provider decision, with
scoped collection access, deletion, rebuild/recovery and common lifecycle evidence
for any adopted provider. There is no required retrieval-quality threshold for selection.

## Phase exit

All five packages record their disposition and dated operational evidence;
record comparison results when performed, without benchmark success thresholds. PostgreSQL and
the chosen S3 provider are operationally covered; any adopted search, graph or
vector provider passes common lifecycle, isolation, capacity and rebuild/recovery
acceptance. All eight performance dashboards have versioned collection,
release-specific capability/evidence records and the verification above, with
external workload dependencies and deployed checks explicitly recorded. Retaining
a baseline is a valid documented experimental decision.
Unrelated Phase 9 work remains open. The separate
[Phase 8 deferred stores](phase-8-deferred-data-stores.md) activates only for its
owner-selected schedule.
