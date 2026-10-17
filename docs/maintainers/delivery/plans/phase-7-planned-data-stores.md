# Phase 7 — Planned Data Stores

Status: planned, unscheduled as of October 17, 2026. PostgreSQL is already
implemented; its baseline and remaining integration acceptance are package 7.1.
Additional stores have no implementation or operational acceptance recorded here.

## Goal and scope

Provide the planned analytical, object-storage, search, graph and vector
capabilities through measured comparisons and optional generic resource providers.
DuckDB/Parquet and one S3-compatible store form the analytical foundation;
OpenSearch, Apache AGE/Neo4j and pgvector/Qdrant follow as targeted experiments.
A planned comparison does not require adoption of every candidate.

**Entry:** existing PostgreSQL platform capabilities and agreed cross-project
integration contract. Complete package 7.1 before introducing additional stores;
then follow analytics/object storage → search → graph → vector package order,
subject to each package's fixtures. Phase 5 AI operations does not depend on
vector retrieval. Optional Phase 6 and unrelated Phase 9 leftovers do not gate
this work.

**Ownership and evidence:** [common acceptance and responsibilities](data-store-expansion.md#ownership-and-common-acceptance)
apply to every package. Track PLAN-026–030 in the
[backlog](../backlog.md#data-store-expansion-tasks); external projects retain
benchmarks, adapters and domain assertions.

## Ordered work packages

### 7.1 — PostgreSQL Baseline and Integration

**Task:** PLAN-026. **Source:** phase 0. **Entry:** existing PostgreSQL platform
capabilities and agreed external integration contract.

- Complete ODIP → VEF deployment acceptance for Energy, linking the generic
  platform evidence and external domain assertions in the
  [energy-system integration plan](energy-system-integration.md).
- Exercise PostgreSQL provisioning and recovery; document JSONB, full-text search,
  recursive CTEs, materialized views, partitioning, and transactional-outbox baselines.
- Reuse existing Phase 9 evidence and record newly performed integration/recovery
  checks against their original tasks; do not close unrelated leftovers.

**Exit:** a versioned cross-project acceptance record and reproducible PostgreSQL
reference establish the gate for introducing additional stores. Local-only
integration or the imported roadmap's starting-point claims do not satisfy it.

### 7.2 — Analytics and S3-Compatible Object Storage

**Task:** PLAN-027. **Source:** phase 1. **Entry:** package 7.1 integration acceptance.

- ODIP compares PostgreSQL and DuckDB on the same versioned energy data:
  daily/monthly aggregation, generation/weather joins, windows, scenario costs,
  and increasing data volumes. Separate query-engine and physical-storage effects.
- Compare PostgreSQL raw artifacts with immutable, versioned S3/Parquet artifacts:
  large-object streaming, checksums, versioning, backup/recovery, and cost.
- Evaluate RustFS, Garage, and MinIO without preselecting a distribution. Add one
  generic S3-compatible resource provider with project-scoped buckets/credentials,
  policies, limits and lifecycle/recovery coverage under the common acceptance.
  DuckDB is an application analytical engine, not necessarily a shared service.

**Exit:** ODIP publishes and consumes versioned datasets independently of physical
storage, the analytical comparison is reproducible, and the selected object-store
provider passes provisioning and recovery acceptance.

### 7.3 — Full-Text Search

**Task:** PLAN-028. **Source:** phase 2. **Entry:** package 7.2 analytical foundation.

- ODIP compares PostgreSQL FTS and OpenSearch using shared dataset descriptions,
  metadata and documentation; Bot Social posts can follow when available.
- Evaluate ranking, filters, facets, typo handling, incremental updates and latency
  against manually judged queries. Keep hybrid retrieval as a later extension.
- If justified, expose an optional OpenSearch provider; verify index rebuilds and
  source-of-truth/update semantics while PostgreSQL remains authoritative.

**Exit:** judged search-quality and operational evidence supports a baseline or
adoption decision; any introduced provider meets common lifecycle acceptance.

### 7.4 — Graph Data

**Task:** PLAN-029. **Source:** phase 3. **Entry:** package 7.3 comparison decision and
versioned VEF dependency fixtures; Bot Social experiments additionally require Core.

- Compare relational PostgreSQL/recursive CTEs, Apache AGE, and Neo4j Community
  Edition for transitive dependencies, cycles, and change-impact analysis in VEF.
- Extend to Energy compatibility, ODIP lineage, and Bot Social two-to-four-hop
  relationships, mutual contacts and recommendations as external fixtures permit.
- Check extension/version compatibility and feature coverage. Provide optional
  AGE or Neo4j support only as justified by the results and common acceptance.

**Exit:** equivalent graph semantics and measured operational tradeoffs are
recorded, with rebuild/recovery evidence for introduced providers. VEF retains
constraint evaluation and optimization responsibility.

### 7.5 — Vector Retrieval and AI Memory

**Task:** PLAN-030. **Source:** phase 4. **Entry:** versioned retrieval fixtures,
AI/RAG use case and preceding experiment decisions. Phase 5 operations assistance
does not require this package.

- Compare pgvector and Qdrant; include OpenSearch if already introduced. Use ODIP
  dataset discovery, Bot Social topic similarity, Energy documentation, or platform
  knowledge collections with explicit relevance judgments.
- Measure Recall@k, MRR or nDCG, p95 latency, filtering, indexing time, memory,
  and update/deletion behavior. Record embedding model and dataset versions.
- Separate semantic memory, durable agent state, and conversation history. Add
  optional extension/provider support only when retrieval evidence justifies it.

**Exit:** reproducible retrieval-quality results and a provider decision, with
scoped collection access, deletion, rebuild/recovery and common lifecycle evidence
for any adopted provider. Agent memory alone is not an adoption criterion.

## Phase exit

All five packages have dated comparison and acceptance evidence. PostgreSQL and
the chosen S3 provider are operationally covered; any adopted search, graph or
vector provider passes common lifecycle, isolation, capacity and rebuild/recovery
acceptance. Retaining a baseline is a valid documented experimental decision.
Unrelated Phase 9 work remains open. The separate
[Phase 8 deferred stores](phase-8-deferred-data-stores.md) activates only for its
own workload or domain triggers.
