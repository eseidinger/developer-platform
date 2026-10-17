# Phase 8 — Deferred Data Stores

Status: deferred, unscheduled as of October 17, 2026. No activation decision,
additional provider implementation or benchmark acceptance is recorded.

## Goal and activation

Keep TimescaleDB, ClickHouse, Valkey and MongoDB/CouchDB visible without committing
to their deployment. Activate only the package justified by a concrete workload or
domain requirement, a reproducible fixture, a named owner and a resource budget.
Use the PostgreSQL and analytical references from
[Phase 7](phase-7-planned-data-stores.md). Completing every Phase 7 comparison or
another deferred package is not required to activate a justified experiment.

The [common acceptance and responsibilities](data-store-expansion.md#ownership-and-common-acceptance)
apply to every activated package. Track PLAN-031–033 in the
[backlog](../backlog.md#data-store-expansion-tasks). Optional Phase 6 and unrelated
Phase 9 leftovers are independent. No service becomes permanent without measured
value and operational evidence.

## Work packages

### 8.1 — Time Series and OLAP

**Task:** PLAN-031. **Source:** phase 5. **Entry:** realistic data volumes or a
reproducible load generator and a concrete ingestion/analytics bottleneck.

- Compare PostgreSQL and TimescaleDB for continuous ingestion and recent queries;
  compare PostgreSQL and ClickHouse for historical/event analytics, retaining
  DuckDB as a reference for bounded energy datasets.
- Verify the selected TimescaleDB edition's license/features. Add optional
  provider support only after the benchmark and resource budget justify it.

**Exit:** measured scaling and operational tradeoffs support retention or adoption;
any introduced provider demonstrates retention, recovery and common acceptance.
This package is deferred until the workload trigger exists.

### 8.2 — Caching and Realtime

**Task:** PLAN-032. **Source:** phase 6. **Entry:** measurable workload requirements,
with Bot Social Core available for feed/profile/rate-limit scenarios.

- Compare Valkey with indexed PostgreSQL, precomputed results and local application
  caches for profiles, feed rankings, rate limits or frequent ODIP metadata reads.
- Account for invalidation, stale reads, consistency, memory, outages and operating
  effort. Define whether state is disposable or requires persistence/recovery.

**Exit:** measured net value supports a decision; optional Valkey provisioning
passes common acceptance with cache rebuild or durable-state recovery demonstrated.
This package is deferred until a justified workload exists.

### 8.3 — Document Stores

**Task:** PLAN-033. **Source:** phase 7. **Entry:** a concrete domain requirement
that PostgreSQL JSONB does not adequately meet; optional after prior comparisons.

- Compare MongoDB or CouchDB with PostgreSQL JSONB using heterogeneous profiles,
  agent configurations or external payloads with complex updates, indexing and
  schema evolution. Check the specific distribution's license before adoption.
- Introduce a generic provider only if the documented comparison justifies it.

**Exit:** a baseline/adoption decision backed by domain and operational evidence;
any adopted provider passes common lifecycle, backup/recovery and isolation gates.
Dynamic documents alone do not justify another store.

## Phase disposition

Unactivated packages remain deferred. For each activated package record the
trigger, comparison results and baseline/adoption decision. Any introduced
provider must pass common lifecycle, isolation, monitoring and recovery acceptance.
A completed experiment does not close the other deferred packages; record each
package's disposition explicitly before closing this phase.
