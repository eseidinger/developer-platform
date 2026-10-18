# Phase 8 — Deferred Data Stores

Status: deferred, unscheduled as of October 18, 2026. No activation decision or
additional provider implementation is recorded. Measurements and comparisons
for activated stores belong to [Phase 9](phase-9-store-measurement-and-comparison.md).

## Goal and activation

Keep TimescaleDB, ClickHouse, Valkey and MongoDB/CouchDB visible without committing
to their deployment. Activate any package at the owner's discretion, with a
named implementation owner and resource budget. No workload trigger, domain-need
justification or benchmark success criteria are required for store selection.
Use the PostgreSQL and analytical references from
[Phase 7](phase-7-planned-data-stores.md). Completing Phase 9 comparisons or
another deferred package is not required to activate a selected store.

The [common acceptance and responsibilities](data-store-expansion.md#ownership-and-common-acceptance)
apply to every activated package. Track PLAN-031–033 in the
[backlog](../backlog.md#data-store-expansion-tasks). Optional Phase 6 and unrelated
Phase 10 leftovers are independent. Stores may be selected for permanent use at
will, subject to the previously selected operational policies. See the
[selection decision](data-store-expansion.md#store-selection-decision).

## Work packages

### 8.1 — Time Series and OLAP

**Task:** PLAN-031. **Source:** phase 5. **Entry:** owner selects the package.

- Verify the selected TimescaleDB edition's license/features. Add optional
  provider support when selected, within the agreed resource budget. Verify
  scoped access, retention, backup capture and common operational acceptance.

**Exit:** record selection; introduced providers demonstrate retention and common
operational acceptance. Recovery is Phase 10 package 10.13; scaling comparisons
are Phase 9 work.
This package stays deferred until the owner schedules it.

### 8.2 — Caching and Realtime

**Task:** PLAN-032. **Source:** phase 6. **Entry:** owner selects the package;
Bot Social Core is needed only for its feed/profile/rate-limit scenarios.

- If selected, add scoped Valkey provisioning and define whether its state is
  disposable or requires persistence. Verify invalidation, stale-read
  behavior, outage handling and common operational acceptance.

**Exit:** record selection; optional Valkey provisioning passes common acceptance
with defined data retention. Cache rebuild or durable-state recovery is Phase 10
package 10.13; comparative cost is Phase 9 work.
This package stays deferred until the owner schedules it.

### 8.3 — Document Stores

**Task:** PLAN-033. **Source:** phase 7. **Entry:** owner selects the package;
no demonstration that PostgreSQL JSONB is inadequate is required.

- Check the specific distribution's license and introduce a generic provider
  when selected by the owner. Verify scoped updates, indexing, schema changes,
  lifecycle, backup capture and isolation.

**Exit:** record selection; any adopted provider passes common lifecycle,
backup capture and isolation checks. Restore acceptance is Phase 10 package 10.13;
document-model comparison is Phase 9 work;
selection has no domain-need or comparative-success requirement.

## Phase disposition

Unactivated packages remain deferred. For each activated package record the
owner's selection and operational status. Any introduced
provider must pass common lifecycle, isolation, monitoring and backup/purge acceptance.
Deployed recovery acceptance is Phase 10 package 10.13.
Measurements and comparisons are recorded in Phase 9.
A completed experiment does not close the other deferred packages; record each
package's disposition explicitly before closing this phase.
