# PostgreSQL Extension Expansion

Status: complete on November 13, 2026. The new image and API are deployed on
node-01; an opt-in six-extension resource and its data were restored into a
separate VM, with a freshly approved read-only application binding and denied
write. The 8 GiB host reserve held in deployed samples. The disposable source
resource was purged after a verified purge-intent backup, and a second verified
backup captured the final state. Evidence is tracked in the
[PLAN-040 validation record](../../../operators/validation/postgresql-extensions-2026-11-12.md).
Task: **PLAN-040**. Implementation and deployment start after
[PLAN-039 storage scope reduction](storage-scope-reduction.md) is complete.
Decision: [ADR-022](../../../architecture/decisions/ADR-022-postgresql-and-s3-storage-scope.md).

## Outcome and current baseline

Add **TimescaleDB, PostGIS, pgmq, and pg_duckdb** to the shared PostgreSQL
service as opt-in extensions for named PostgreSQL resources. Keep PostgreSQL
and S3 as the platform's project data-store options. These extensions do not
introduce separate project data-store providers or permanently running store
services.

The current production PostgreSQL image includes AGE and pgvector, and the
named-resource contract selects `age` and `vector`. A prior disposable
compatibility check included TimescaleDB, but the production image and public
resource contract do not yet offer it. That check is evidence for its recorded
versions and fixture only; it does not establish compatibility or operational
acceptance for the four-extension target.

Platform maintainers own the image, resource contract, and tests. Operators own
version selection, installation, capacity, backup, upgrades, and deployed
checks. Application owners choose extensions for their named databases and
verify application queries and migrations.

## Work packages

### 1. Select compatible versions and a resource budget

1. After PLAN-039 records the reclaimed CPU/RAM budget, select pinned versions
   or source commits of all four extensions against the supported PostgreSQL
   image. Record build dependencies, license and redistribution requirements,
   PostgreSQL version support, and any preload or server-level settings. Verify
   that required settings can coexist with AGE and pgvector.
1. Test each extension alone, the combinations the platform will advertise,
   and the intended combined configuration in a disposable server. Include
   creation order, restart, ordinary SQL use, and extension upgrade paths.
   Record unsupported combinations explicitly rather than exposing them as
   selectable.
1. Measure idle and representative query CPU, RAM, disk, and startup cost.
   Preserve the host reserve and workload capacity gained by PLAN-039. A
   measured capacity conflict blocks deployment until the configuration or
   budget is resolved.

**Exit evidence:** reviewed version and compatibility matrix, pinned build
inputs, required server settings, and a capacity budget for the supported
combinations.

### 2. Build and expose opt-in extensions

1. Add the reviewed extensions to the pinned PostgreSQL image and its
   reproducible build. Enable only required server-level settings; install
   extensions in a named database only when that resource selects them. Keep
   the platform catalog and unselected project databases free of extension
   objects.
1. Extend the named PostgreSQL resource schema, API capabilities, CLI, portal,
   generated client types, and documentation for `timescaledb`, `postgis`,
   `pgmq`, and `pg_duckdb`. Validate selected combinations before provider
   side effects. Keep extension installation and upgrade under operator control;
   human and workload data roles do not receive server administration rights.
1. Review each extension's schema ownership, object permissions, background
   work, network and file access, and any access to S3. Enforce project and
   resource isolation and the existing grant model, including read-only denial
   of writes. Do not make object-storage credentials available to SQL roles
   without an explicit, scoped platform contract.

**Exit evidence:** opt-in resource creation and use work through the supported
clients; unsupported selections are rejected before side effects; plain
PostgreSQL resources and other projects cannot use or administer unselected
extension capabilities.

### 3. Verify data lifecycle and recovery

1. Exercise representative time-series, spatial, queue, and analytical SQL
   workloads with the selected extensions. Verify application migration,
   credential rotation and revocation, query permissions, quotas or resource
   bounds, and isolation across two projects. Check interactions with existing
   AGE and pgvector resources.
1. Take the normal encrypted off-host backup and restore into a disposable
   server with the pinned extension versions. Verify data, extension objects,
   queue state where retained, S3 references where used, roles and grants,
   application reconnection, and the existing purge-intent rules. Document
   extension-specific recovery and upgrade ordering; a successful SQL dump
   alone is not proof that extension behavior recovered.
1. Run a controlled PostgreSQL upgrade and rollback rehearsal using the
   supported procedure. Record what can be rolled back and what requires
   restoration after an extension or storage-format change. Verify monitoring
   and alerts for extension-related failures and resource pressure.

**Exit evidence:** source, local real-PostgreSQL, and deployed acceptance for
the supported extension set, with versioned backup/restore and capacity results.
Failures keep the affected extension unavailable for new resources until the
specific compatibility or recovery gap is resolved.

## Sequencing and handoff

Preparation and version research may run while PLAN-039 is in progress.
Changing the installed PostgreSQL image, public extension selection, or live
databases waits until PLAN-039 is complete and its workload-capacity baseline is
recorded. This keeps the capacity gain measurable before adding extension
costs. Update the operator store guide, image/build documentation, API examples,
and verification register as implementation advances. Do not mark PLAN-040
complete on a successful disposable fixture alone.
