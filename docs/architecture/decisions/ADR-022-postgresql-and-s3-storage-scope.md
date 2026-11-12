# ADR-022 – PostgreSQL and S3 Storage Scope

Created and accepted: November 12, 2026. Status: **Accepted direction;
implementation and migration pending**.

## Context

The platform has accumulated several project data-store providers and their
supporting services. Operating them consumes CPU and RAM and adds provisioning,
access, backup, recovery, monitoring, and upgrade work. This reduces the
resources available to hosted workloads on the single-host lab.

## Decision

Keep **PostgreSQL, including its extensions, and S3-compatible object storage**
as the platform's project data-store options. Remove the other project
data-store providers and their dedicated services from the platform. Do not add
new non-PostgreSQL, non-S3 project stores to this platform.

Create a **separate storage lab project** for experiments with other storage
options. That project is planned; this decision does not claim it exists yet.
PostgreSQL extension experiments can remain on the platform when they fit the
PostgreSQL service's capacity and operational safeguards.

**Post-reduction extension decision (November 12, 2026):** After
[PLAN-039](../../maintainers/delivery/plans/storage-scope-reduction.md) is
complete, extend the shared PostgreSQL service with **TimescaleDB, PostGIS,
pgmq, and pg_duckdb**. The
[extension plan](../../maintainers/delivery/plans/postgresql-extension-expansion.md)
owns compatibility, isolation, capacity, and recovery acceptance. This is
planned scope, not a claim that the extensions are installed or available to
projects.

This decision concerns project data-store offerings. Platform dependencies such
as identity, monitoring, and backup storage are outside this scope.

## Consequences

The smaller provider set reduces platform complexity and returns CPU and RAM
budget to application workloads. Work on non-retained providers in the earlier
data-store roadmap and Phases 7–9 is superseded. Existing implementations and
deployed resources do not disappear when this decision is recorded.

Retire affected providers and services through the
[storage scope reduction plan](../../maintainers/delivery/plans/storage-scope-reduction.md).
Inventory any live resources and consumers, arrange a supported migration or
export where needed, preserve required backup and retention safeguards, and
verify resource retirement before reclaiming capacity. Update API capabilities,
UI, CLI, documentation, and tests as the implementation changes. Retain the
PostgreSQL and S3 lifecycle, access, backup, and recovery requirements.

## Alternatives

Continuing to run all selected stores on the platform preserves a broad catalog
but retains their CPU, RAM, and operational cost. Removing S3 would further
reduce services but would also remove the platform's object-storage option.
The selected scope keeps object storage while giving other store experiments a
separate place.

## Validation

For the implementation, verify that PostgreSQL, its supported extensions, and
S3 remain usable; removed providers cannot be selected; affected data and
credentials are handled according to the retirement plan; and measured
platform-service CPU and RAM use leaves more capacity for workloads. Record
the result in the delivery evidence rather than treating this ADR as proof of a
completed removal.
