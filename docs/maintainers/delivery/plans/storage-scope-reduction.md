# Storage Scope Reduction

Status: planned November 12, 2026; no migration, deployment change, or data
deletion is recorded by this plan. Task: **PLAN-039**. Decision:
[ADR-022](../../../architecture/decisions/ADR-022-postgresql-and-s3-storage-scope.md).

## Outcome and boundary

The Developer Platform offers only named PostgreSQL resources, including their
supported extensions, and S3-compatible object storage. Remove the OpenSearch,
Qdrant, Neo4j, CouchDB, and HugeGraph project providers and their dedicated
services. Keep the existing PostgreSQL and S3 resource lifecycle, access,
backup, recovery, and monitoring behavior. Keep platform dependencies such as
identity, telemetry, and backup infrastructure; they are outside ADR-022's
project data-store scope.

Create a separate storage lab project for other storage options and comparisons.
Do not transfer live project data or credentials to that lab as part of source
cleanup. The existing Phase 7–9 provider and comparison plans remain historical
evidence, not active acceptance gates for this platform.

Platform maintainers own the contract and source changes; operators own live
inventory, backup, retirement, service shutdown, and capacity evidence.
Application owners own any data-model migration and verification of their
workloads. Record an owner and disposition for each affected resource before
changing its service.

## Work packages

### 1. Inventory and establish the baseline

1. Record the deployed revision and configuration. Inventory every non-retained
   resource by provider, project, state, grants, human leases, component
   bindings, dependent application, and data owner. Include retained or
   `PurgeAwaitingVerifiedBackup` resources and resources outside the current
   deployment's selected Compose profiles.
1. Inventory provider services, dedicated Neo4j instances, native consoles,
   volumes, backup contents, monitoring targets, routes, secrets, and operator
   configuration. Record whether each resource contains authoritative data or
   only a rebuildable projection.
1. Capture a repeatable host CPU/RAM baseline under representative workloads,
   including platform services, selected stores, tracing, backups, and workload
   demand. Record the existing host reserve and the capacity currently assigned
   to non-retained services.

**Exit evidence:** a versioned inventory and capacity baseline with an owner,
consumer, retention requirement, and migration or retirement disposition for
every non-retained resource. Do not include credential values or application
data in the evidence.

### 2. Freeze new non-retained resources

1. Make the server reject creation of OpenSearch, Qdrant, Neo4j, CouchDB, and
   HugeGraph resources regardless of client or stale capability data. Remove
   these options from advertised capabilities, CLI, portal, examples, and new
   application guidance. Keep existing-resource reads and retirement operations
   available while migration is in progress.
1. Preserve PostgreSQL extension selection and S3 creation. Verify the
   PostgreSQL and S3 API contract, component bindings, human access, and
   supported consoles still work. Do not conflate a PostgreSQL extension with a
   separate provider when narrowing the contract.
1. Test that a request for a removed provider fails before catalog or native
   side effects. Check direct API calls as well as portal and CLI behavior.

**Exit evidence:** new non-retained resources cannot be created, while existing
ones remain manageable for safe disposition and retained stores remain usable.

### 3. Migrate consumers and retire resources

1. For each affected authoritative resource, agree with its application owner
   on a PostgreSQL/extension or S3 destination, an export or transformation, a
   cutover window, and a way to verify domain data. Where there is no valid
   destination, keep the old resource protected and record the unresolved
   decision; do not claim it has been migrated. Rebuildable projections may be
   dropped only after their inputs and rebuild procedure are verified. Use only
   extensions already supported on the platform for this cutover; the
   [four-extension expansion](postgresql-extension-expansion.md) follows
   PLAN-039.
1. Take and verify the required encrypted off-host backup before cutover. Migrate
   data, update component bindings and credentials, and check application
   behavior, counts or checksums, isolation, and reconnection on the retained
   store. Record how to recover if the cutover fails.
1. Retire old resources through their normal lifecycle. Confirm grant, lease,
   Secret, network, and console-session revocation. Use the existing
   resource-specific purge preview and confirmation only when the data owner and
   retention requirements permit it. Wait for the scheduled backup to capture
   and verify the exact purge intent before accepting `purged` as observed
   state. Preserve historical ownership, audit, and backup-retention records.

**Exit evidence:** every non-retained resource is either demonstrably migrated
and purged or remains explicitly tracked as a blocker. A stopped service, empty
lease list, or missing Compose profile is not evidence of data deletion.

### 4. Remove provider implementation and services

1. After no live resource needs a provider, remove its runtime adapter,
   registration, provisioning, credential, relay, console, dashboard, and backup
   paths. Narrow public create schemas and generated clients. Preserve a way to
   read historical catalog and audit records without calling removed native
   providers; migrate persistent constraints only after checking stored rows.
   Keep a documented, version-pinned recovery route for pre-removal snapshots
   until their retention period ends, so source cleanup does not orphan backups.
1. Remove non-retained Compose profiles, service definitions, Ansible options,
   setup scripts, secrets, monitoring targets, and operator instructions. Stop
   services through a controlled operator rollout. Remove provider volumes only
   after the verified retirement and backup gates, with an inventory of what is
   being deleted. Retained PostgreSQL, S3, and platform services must stay
   healthy throughout.
1. Remove obsolete provider tests and fixtures while keeping coverage for the
   create rejection, historical-record behavior, retained-store lifecycle,
   extension compatibility, S3 access, backup/recovery, and isolation.

**Exit evidence:** the supported contract and installed services contain only
PostgreSQL and S3 as project data-store options; no unresolved live resource
depends on removed code or volumes. Old catalog and audit history remain
readable. Source, local, and controlled deployed checks pass.

### 5. Verify capacity and establish the storage lab

1. Repeat the baseline CPU/RAM measurement with comparable workloads and the
   same observability settings. Record which service reservations and actual
   usage were removed, the resulting host reserve, and the workload capacity
   available. Investigate any missing gain before claiming the decision's
   capacity objective is met.
1. Create the separate storage lab project with its own infrastructure and
   operating budget. Move or recreate comparison instructions and disposable
   fixtures there as appropriate, without live credentials or project data.
   Link the lab from the product roadmap when it exists; until then, keep its
   status explicitly planned.

**Exit evidence:** reproducible before/after capacity results and a working,
separately owned storage lab. The lab's creation does not gate safe retirement
of unused providers on this platform.

## Release and recovery rules

Each rollout stage requires a documented rollback or recovery path before it
changes live state. The creation freeze can be reversed while provider code and
services still exist. Migration and purge require verified backups and their
own recovery procedures; an older image or re-enabled Compose profile cannot
recover purged data by itself. If an inventory item, backup, migration check,
credential revocation, or retained-store regression fails, stop that provider's
retirement and keep its protected data and service available until resolved.

Do not mark PLAN-039 complete until all non-retained resources and services have
the recorded disposition, retained-store checks pass, before/after capacity
evidence is published, and the separate storage lab exists with its own
completion evidence under work package 5.

After this gate, PLAN-040 may add TimescaleDB, PostGIS, pgmq, and pg_duckdb to
PostgreSQL. Its installation and capacity results are separate from PLAN-039's
measured reduction.
