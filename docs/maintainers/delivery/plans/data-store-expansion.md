# Data Store Expansion

Status: planned and deferred work as of October 17, 2026. PostgreSQL provisioning
is implemented; the additional data-store providers below are not implemented in
the inspected platform source. No new deployment or benchmark was performed for
this documentation update.

The [data store roadmap](../../../product/data-store-roadmap.md) is organized into
two platform phases:

| Phase | Scope | Tasks |
|---|---|---|
| [7 — Planned Data Stores](phase-7-planned-data-stores.md) | PostgreSQL baseline/integration, DuckDB/Parquet/S3, OpenSearch, AGE/Neo4j, pgvector/Qdrant | PLAN-026–030 |
| [8 — Deferred Data Stores](phase-8-deferred-data-stores.md) | TimescaleDB, ClickHouse, Valkey, MongoDB/CouchDB | PLAN-031–033 |

Data-store phases precede leftovers in delivery order: Phase 7 planned stores,
Phase 8 deferred stores, then Phase 9 anytime leftovers. This renumbers the
former Phases 8, 9 and 7 respectively and replaces the initial eight-phase breakdown. Existing task IDs and acceptance
criteria are retained as packages within the two phases. Phase 7 incorporates
source roadmap phases 0–4; Phase 8 incorporates source phases 5–7. Optional Phase 6
compute/service expansion is independent. [Phase 9 leftovers](phase-9-anytime-leftovers.md)
remains last, anytime and lowest priority. Only the integration/recovery checks
specifically needed for a store gate that package; completing all of Phase 9 is
not a prerequisite.

## Ownership and common acceptance

The platform owns generic resource provisioning, secrets and bindings, network
policy, lifecycle, backups/recovery, monitoring, quotas, and retirement. ODIP owns
the shared experiment framework, dataset versions, adapters, and analytical/search
comparisons. VEF owns dependency/constraint semantics; Energy and Bot Social own
their domain scenarios. Bot Social Core (bots, profiles, posts, relationships and
reproducible synthetic load) is an external prerequisite for its experiments.
No application-specific profile or benchmark logic belongs in the Platform API.

Extend the current Kubernetes provider and Python API through a shared resource
specification with store-specific provider schemas. PostgreSQL remains the
reference and initially authoritative store. Search, graph, and vector indexes
should be rebuildable projections where appropriate; document each source of
truth and evaluate a transactional outbox before adding event infrastructure.
Kafka or NATS JetStream requires evidence for replay, independent consumers,
decoupling, or event volume.

Every activated provider must demonstrate provisioning/reconciliation, retry and
restart behavior, scoped access and revocation, managed secret rotation/redaction,
network isolation, bounded capacity, health/alerts, upgrade/rollback, and retirement
with explicit retention/deletion policy. Record backup and measured recovery for
authoritative data; demonstrate rebuild and reconcile retained configuration for
derived indexes. Document supported versions, license, maturity, operating model,
and recovery ownership before selection. Use the existing lab under its recorded
validation policy, with bounded impact and recovery steps; do not provision another
test environment. Run specialized stores individually with resource limits until
measured value and capacity justify permanent operation. Recheck host capacity;
the source roadmap's VM figures are not verified sizing evidence.

Each comparison records versioned data, reproducible workload and environment,
equivalent results, p50/p95 latency, throughput, scaling, CPU/RAM/disk/index size,
import/update/delete/rebuild, consistency and coupling, deployment/recovery/upgrade,
and infrastructure, maintenance and license costs. Isolated performance comparisons
may use the local workstation. The outcome is a documented decision to retain the
baseline, adopt the alternative, or run another test; comparison alone does not
commit the platform to a permanent service.

Execution and evidence: [PLAN-026–033](../backlog.md#data-store-expansion-tasks).
Assign named platform and external experiment owners before each phase starts.

