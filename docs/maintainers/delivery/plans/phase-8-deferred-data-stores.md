# Phase 8 — Deferred Data Stores

Status: deferred, unscheduled as of October 17, 2026. No activation decision,
additional provider implementation or benchmark acceptance is recorded.

## Goal and activation

Keep TimescaleDB, ClickHouse, Valkey and MongoDB/CouchDB visible without committing
to their deployment. Activate any package at the owner's discretion, with a
named implementation owner and resource budget. No workload trigger, domain-need
justification or benchmark success criteria are required for store selection.
Use the PostgreSQL and analytical references from
[Phase 7](phase-7-planned-data-stores.md). Completing every Phase 7 comparison or
another deferred package is not required to activate a selected experiment.

The [common acceptance and responsibilities](data-store-expansion.md#ownership-and-common-acceptance)
apply to every activated package. Track PLAN-031–033 in the
[backlog](../backlog.md#data-store-expansion-tasks). Optional Phase 6 and unrelated
Phase 9 leftovers are independent. Stores may be selected for permanent use at
will, subject to the previously selected operational policies. See the
[selection decision](data-store-expansion.md#store-selection-decision).

## Work packages

### 8.1 — Time Series and OLAP

**Task:** PLAN-031. **Source:** phase 5. **Entry:** owner selects the package;
use realistic data or a reproducible load generator for any scaling comparison.

- Compare PostgreSQL and TimescaleDB for continuous ingestion and recent queries;
  compare PostgreSQL and ClickHouse for historical/event analytics, retaining
  DuckDB as a reference for bounded energy datasets.
- Verify the selected TimescaleDB edition's license/features. Add optional
  provider support when selected, within the agreed resource budget.

**Exit:** record selection and any scaling/operational observations; introduced
providers demonstrate retention, recovery and common operational acceptance.
This package stays deferred until the owner schedules it.

### 8.2 — Caching and Realtime

**Task:** PLAN-032. **Source:** phase 6. **Entry:** owner selects the package;
Bot Social Core is needed only for its feed/profile/rate-limit scenarios.

- Compare Valkey with indexed PostgreSQL, precomputed results and local application
  caches for profiles, feed rankings, rate limits or frequent ODIP metadata reads.
- Account for invalidation, stale reads, consistency, memory, outages and operating
  effort. Define whether state is disposable or requires persistence/recovery.

**Exit:** record selection and any comparison observations; optional Valkey
provisioning passes common acceptance with cache rebuild or durable-state recovery.
This package stays deferred until the owner schedules it.

### 8.3 — Document Stores

**Task:** PLAN-033. **Source:** phase 7. **Entry:** owner selects the package;
no demonstration that PostgreSQL JSONB is inadequate is required.

- Compare MongoDB or CouchDB with PostgreSQL JSONB using heterogeneous profiles,
  agent configurations or external payloads with complex updates, indexing and
  schema evolution. Check the specific distribution's license before adoption.
- Introduce a generic provider when selected by the owner.

**Exit:** record selection and any document-model observations; any adopted
provider passes common lifecycle, backup/recovery and isolation checks. Selection
has no domain-need or comparative-success requirement.

## Phase disposition

Unactivated packages remain deferred. For each activated package record the
owner's selection, comparison results when performed and operational status. Any introduced
provider must pass common lifecycle, isolation, monitoring and recovery acceptance.
A completed experiment does not close the other deferred packages; record each
package's disposition explicitly before closing this phase.
