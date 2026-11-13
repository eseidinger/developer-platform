# PLAN-040 PostgreSQL extension validation, November 12, 2026

This record distinguishes local image and component evidence from deployed
acceptance. The [PLAN-039 capacity comparison](storage-scope-2026-11-12.md)
measured 22,653 MiB mean host available memory after removing the retired
stores, up 2,009 MiB from the preceding 15-minute window. PostgreSQL retains
its 2 GiB container memory ceiling and one CPU ceiling. PLAN-040 must preserve
the 8 GiB host reserve and the capacity returned to application workloads.

## Reviewed image inputs

The image uses PostgreSQL 18.6 on the existing immutable base-image digest.
The source checkout commits below are checked in the Dockerfile. PostGIS uses
the pinned PGDG package and retains its Debian copyright file in the image.

- **pgvector:** 0.8.7, commit
  `f37c13f68b57d2c3472b2214fbcff699d6d34876`. Previously validated on
  PostgreSQL 18. PostgreSQL License; no preload.
- **AGE:** PG18/v1.8.0-rc0, commit
  `e43dc1a12b78fba4acef9835b2b10379b8d243b4`. PG18 branch, Apache 2.0;
  preload `age`.
- **TimescaleDB:** [2.31.0](https://github.com/timescale/timescaledb/releases/tag/2.31.0),
  commit `4fa2a7c6b579171a1a8966fd87a0d4189ebab43b`. Supports PG16–18.
  [Apache 2.0 and Timescale License](https://github.com/timescale/timescaledb/blob/2.31.0/LICENSE)
  for `-tsl` binaries; preload `timescaledb`, telemetry off.
- **PostGIS:** [PGDG package](https://apt.postgresql.org/pub/repos/apt/)
  `3.6.4+dfsg-2.pgdg13+1`. [Supports PG12–18](https://www.postgis.net/development/compatibility/).
  GPL-2+ with dependency notices; no preload.
- **pgmq:** [1.13.0](https://github.com/pgmq/pgmq/releases/tag/v1.13.0),
  commit `32c075bb6dbed66a303d1a792393c93e36c09a97`.
  [Supports PG14–18](https://github.com/pgmq/pgmq/blob/main/pgmq-extension/README.md).
  PostgreSQL License; SQL only, no worker.
- **pg_duckdb:** [1.2.0](https://github.com/duckdb/pg_duckdb/releases/tag/v1.2.0),
  commit `8756099e267c47f0b86c24de4cf995327f1f4279`.
  [Supports PG14–18](https://github.com/duckdb/pg_duckdb/blob/main/docs/compilation.md).
  MIT; preload `pg_duckdb`.

The build stage adds CMake, Ninja, ICU, curl, LZ4, PostgreSQL headers, and a
C/C++ toolchain for TimescaleDB and pg_duckdb. The runtime carries PostGIS,
curl and LZ4 libraries. The pg_duckdb source tag pins its DuckDB submodule;
`ReleaseStaticSystem` links that revision into the extension. Source license
files and notices are copied into `/usr/share/doc/platform-extensions/`.

The server sets `duckdb.postgres_role=platform_duckdb_user`,
[external access](https://github.com/duckdb/pg_duckdb/blob/v1.2.0/docs/settings.md)
off, automatic DuckDB extension installation and loading off, 128 MiB maximum
DuckDB memory and two DuckDB threads per connection. Only selected resource
writers inherit that role. Local files, HTTP, and S3 are unavailable through
DuckDB SQL; no S3 credentials are passed to PostgreSQL. `duckdb.raw_query` is
revoked from PUBLIC in selected databases.

## Local compatibility and cost

The final local image `sha256:e99eabbdbb1b8b56744c140785b3bb457893ee56faf2d1f333bfdb0e2957ab12`
measured 1,220,205,195 bytes, versus 655,183,071 bytes for the AGE/pgvector
image, an increase of 565,022,124 bytes. This is image storage, not a measured
host RAM increase. The isolated container, limited to one CPU and 2 GiB RAM like
the deployed service, became ready in 2.42–2.55 seconds in two runs.

An isolated PostgreSQL 18.6 container created all 63 nonempty subsets of the
six extension names in the fixed order `vector`, `age`, `timescaledb`, `postgis`,
`pgmq`, `pg_duckdb`; every subset installed successfully. Reverse creation of
the full set exposed a real conflict: pg_duckdb creates `time_bucket` before
TimescaleDB can create its function. The provisioner now sorts extension
installation into the tested order regardless of API request order. The full
resource fixture uses reversed API order to test this normalization. An
operator restoring or upgrading extension objects must use that order.

The managed writer created a TimescaleDB hypertable, inserted spatial data,
sent a pgmq message and ran a DuckDB analytic query. The read-only identity
could query the time-series and spatial data but could not insert, send a queue
message, or run DuckDB. The writer could not read `/etc/passwd` through DuckDB
or call `duckdb.raw_query`; the writer could not connect to a plain resource
database. A restart preserved time-series, queue and DuckDB query behavior.
A bounded mixed workload then inserted 100,000 hypertable rows and 10,000
spatial rows, built a GiST index, sent 100 queue messages, and ran a DuckDB
million-row aggregation. Two runs took 0.26–0.27 seconds of wall time and 0.26
CPU seconds. Container cgroup memory peaks were 68,206,592–93,249,536 bytes
(65.05–88.93 MiB), and the resource database measured 27,522,751 bytes.
Idle post-restore Docker samples reported 0.08% CPU and 87.8–94.74 MiB RAM
inside the 2 GiB limit.
This is a small isolated workload; concurrent application sessions and backup
pressure need deployed measurement before the host budget is accepted.

`pg_dump -Fc` and `pg_restore` into a new database with the TimescaleDB
pre/post-restore hooks succeeded. The restored hypertable value, spatial
coordinate, queue message count and DuckDB query all matched. `pg_dump` warned
of circular foreign keys in TimescaleDB's `continuous_agg` catalog; the full
dump restored successfully. The local fixture does not replace the normal
encrypted off-host backup and recovery acceptance.

The same fixture then streamed the production `pg_dumpall` format into a fresh
PostgreSQL 18.6 container. Hypertable values, spatial coordinates, the pgmq
message count, and a DuckDB query matched. The only restore diagnostics were
expected pg_duckdb `time_bucket` coexistence warnings. This validates the SQL
format used inside the encrypted bundle; it does not prove off-host restic
recovery or application reconnection.

The application suite passed 514 tests with 14 skips. The UI contract, lint,
format, typecheck, unit and build checks passed. The PostgreSQL extension
presence alert passed its `promtool` rule test. The existing named PostgreSQL
fixture passed against the new image with AGE and pgvector selected, including
real graph rebuild after logical restore, cross-writer changes, reader denial,
credential rotation, relay expiry, and isolated purge.

A separate disposable-volume rehearsal switched the existing pgvector
database from the old image to the new image and back to the old image. The
vector query and extension catalog remained valid at every step. This
same-major rollback is valid before a new extension writes data; it does not
prove rollback of a TimescaleDB or pg_duckdb storage-format change.

The existing named-resource fixture also created an encrypted Restic backup
with the old AGE/pgvector image and restored it into an empty server running
the new image. SQL/catalog data, graph rebuild, vector queries, restore
quarantine, purge intent, credential revocation, and fresh read-only approval
passed. This used a disposable local repository and does not establish that
the external repository can be recovered on a separate host.

## Deployment gate

No live PostgreSQL image or project database was changed in this record. The
latest read-only host check showed 22,695 MiB available RAM and 210 GiB free
disk. A fresh encrypted off-host backup completed and readback verified as
snapshot
`ea660b11758f57f3db41c141280e7bcb6c79cc0108cdd23048bbd43ac9035301`
at 18:31:32 UTC. A disposable Ubuntu 24.04 QEMU/KVM guest is running in WSL
at 127.0.0.1:2222. Its restore imported SQL, checked the latest purge
intent, quarantined restored access, and restored Caddy, Grafana, and RustFS
volumes. The recovered old PostgreSQL image was the tagged image
`sha256:40b6a189fa6d13340bc96529a2b3c36da464b19558eaa71c7cef711b75fdeb7f`.
The running production container reports image ID
`sha256:6cb1d00abe9fcf887a3c88f4827d3a194741b52bb997918ec429f1b43a92584d`,
whose image object is no longer retained by Docker. Direct SHA-256 comparison
between the running container and the tagged image matched the PostgreSQL
server binary (`4944085dba4a`), AGE library (`d426f351fd4c`), and pgvector
library (`883df4b860c2`). The full image IDs are therefore not identical;
this drill establishes matching server and selected extension binaries.
The legacy bundle omitted `.env.example`; the staged defaults file matched
the production source checksum
`80ecae1ebdf28632b3a205f24ce3fc6af56ab6855caab94aadfc05fa8692247e`.
The first restored platform started successfully; acceptance findings follow.

The first fresh-VM run restored that snapshot and started the platform. It
correctly refused to reapply `vareng-test`: all four active projects in the
snapshot have store bindings, and recovered grants are revoked. In the isolated
guest, an unbound public HTTP echo application passed API, ingress and core
monitoring checks. The active `vareng-test` named PostgreSQL resource passed
catalog, SQL and revoked-access checks. The private reports are in
`.runtime/recovery-evidence/recovery_vm/plan040-2026-11-12/`. These checks did
not establish historical data recovery or reconnect a bound application.

To prove historical SQL recovery, a marker was committed in the retired test
resource `b7725b16-98dc-4feb-800a-ce6ec9ff618e`, which has AGE and pgvector.
Its private receipt was copied independently to the controller before backup;
SHA-256 matched at both locations. The normal encrypted backup then completed
with readback verification as snapshot
`6c2aeef56fa13b7d272b9f546c3d4acccdf4019f787792692be135cf05a29427`
captured at 20:56:56 UTC. A new empty recovery VM restored this snapshot and
started the old PostgreSQL image and platform. Its first one-shot playbook run
stopped after platform startup because the helper called `k3d` through `PATH`;
the binary is installed at `.runtime/bin/k3d`. The helper now uses that exact
path. The interrupted VM then imported the image into k3d, issued a
recovery-only test credential, reconciled the latest verified store intents,
and checked the named resource. Its private report in
`.runtime/recovery-evidence/recovery_vm/plan040-2026-11-12-marker/` passed with
`historical_data_verified: true` and `quarantine_verified: true`. The marker
receipt SHA-256 matched the independent controller copy. This proves historical
SQL from the external encrypted backup on a separate host, but does not prove
application reconnection.

A second fresh VM completed the full one-shot playbook with the reviewed
PLAN-040 image
`sha256:e99eabbdbb1b8b56744c140785b3bb457893ee56faf2d1f333bfdb0e2957ab12`.
The running server advertised TimescaleDB 2.31.0, PostGIS 3.6.4, pgmq 1.13.0,
and pg_duckdb 1.2.0, with the required preload libraries. The fetched private
report at `.runtime/recovery-evidence/recovery_vm/20261112T212319/` passed
`historical_data_verified: true` and `quarantine_verified: true`. It records
`application_reconnected: false`; the selected retired resource has no
automatically reapproved application binding. After both reports passed, the
exact one-row source marker table was checked against its independent receipt
and removed transactionally from the retired test database. The verified
snapshot retains the marker for future replay.

## Deployed image and remaining acceptance

After marker cleanup, the normal encrypted backup completed with readback
verification as snapshot
`ee823420a226a3288ed6ffbae8f1f44662ec1924c4d87e3a2309674ce58e966c`.
The production host had 22,635 MiB available RAM and 210 GiB free disk before
deployment. Ansible then deployed clean source revision
`f11bafccacb80519fc48c8683e79d1c849508e7f`; its installation record has
that exact revision. The controlled Compose restart finished successfully.
The running PostgreSQL image ID is
`sha256:72e7c2712240a2d0d7458f8e43932b62262c4a7ae1b62abf25f2203ac4779b61`.
It reports TimescaleDB 2.31.0, PostGIS 3.6.4, pgmq 1.13.0, and pg_duckdb
1.2.0 available, with `timescaledb,age,pg_duckdb` preloaded. PostgreSQL,
internal API, and public API readiness passed. Host available RAM after the
restart was 23,552 MiB, above the 8 GiB reserve; PostgreSQL used 139.5 MiB in
one idle sample under its unchanged 2 GiB limit. Disk free was 204 GiB.
The server, AGE, pgvector, TimescaleDB, PostGIS, and pg_duckdb binary SHA-256
digests all matched the locally validated candidate image despite the distinct
Docker image IDs. A later sample with bound workloads running showed 23,624
MiB host available RAM and PostgreSQL at 145.2 MiB within its 2 GiB limit.

The existing retired AGE/pgvector resource still had `age` 1.8.0 and `vector`
0.8.7 installed. An active plain resource and the platform database had only
`plpgsql`; new extensions were not installed implicitly. Prometheus loaded the
`PostgreSQLExtensionMissing` alert. The public OpenAPI schema advertised all
six supported extension names for `ResourceCreate`. Scheduled ingestion jobs
failed in both `odip` and `odip-test` at 21:58–22:00 UTC during maintenance;
their jobs from 22:01 through 22:05 UTC succeeded after the API and database
returned.

The freshly installed backup runner then completed a normal encrypted backup
with readback verification as snapshot
`39e9b2c7e0fe7f39e77f315dbd995f87d3093ee4d47fcd3bf1f6a4a47bc8789c`.
This validates capture with the deployed source and image configuration; it
precedes creation of new extension data and therefore does not yet establish
their restore behavior.

A disposable resource `3b1f9806-b4a3-4121-8bc5-1c50c0a2d995` in the active
`vareng-test` project selected all six extensions in reverse API order and
reached `observed_state=active`. An unsupported extension request returned HTTP
422 and left the resource catalog unchanged. The selected database installed
AGE 1.8.0, pgvector 0.8.7, TimescaleDB 2.31.0, PostGIS 3.6.4, pgmq 1.13.0,
and pg_duckdb 1.2.0. SQL readback found a hypertable value sum of 42, a
PostGIS longitude of 13, one queued pgmq message, a DuckDB result of 42, and
pgvector distance 1. PostGIS and pgvector live in the managed
`platform_extensions` schema, so operator SQL explicitly included that schema
in its search path. With this resource active, PostgreSQL used 243.1 MiB of
2 GiB, with a 529 MiB container peak since restart; host available memory was
23,396 MiB.

An independent SQL marker was committed in that resource. Its source and
controller receipt SHA-256 matched
`624c5919dd57ccb818fd26b71a32ddfb4aa3d965f0c502067be1dcbcf62db162`.
The normal encrypted backup then completed with readback verification as
snapshot
`28dfdde90e173e8082042bd71317e4767b6559230c66095c26b3082f5106989b`.
A third fresh WSL VM completed the official one-shot restore with the reviewed
image. Its private report in
`.runtime/recovery-evidence/recovery_vm/20261112T222229/` passed historical
marker and quarantine checks for the exact resource. Manual readback on the
restored server found all six installed extension versions and the same
hypertable sum 42, longitude 13, one queued message, DuckDB result 42, and
vector distance 1. The official named-store report still says
`application_reconnected: false`, because it checks only catalog and SQL. A
supplemental VM-only project then requested and explicitly approved a fresh
cross-project read-only binding. Its scheduled PostgreSQL application read the
restored value and succeeded only after a write attempt was denied. The private
`reconnect-app.json` report and completed job `reader-29908720` record this
check. Since the fixture table was created by the operator `postgres` rather
than the resource owner, the VM operator granted SELECT on that table to the
resource reader role after restore; this supplemental check does not claim that
default privileges for owner-created tables were exercised. The local fixture
already covers those default privileges.

The local bounded mixed workload and deployed samples with the all-extension
resource showed no conflict with the unchanged 2 GiB PostgreSQL ceiling or the
8 GiB host reserve. These samples do not measure long-running peak concurrency.
The old and candidate image local rollback fixtures do not justify switching
an already migrated database to the old image.

On November 13, the disposable source resource
`3b1f9806-b4a3-4121-8bc5-1c50c0a2d995` was retired and its purge requested
through the API with a fresh human admin authorization. The controller waited
for the required verified backup of the purge intent, snapshot
`6fd0d552a98058a5b0b25bb2ea8610c8f998973c2f0f841e2230cfabacd4d518`.
It then marked the exact resource `purged` with observed state `purged`; its
PostgreSQL database was absent. A second normal encrypted backup completed with
readback verification after the purge as snapshot
`a8e69241ab416841763153c076e18de6d34726a019cf04739daf827f86bf5af4`.
The backup service was inactive afterward, and the one-time local admin token
file was removed. Host available memory was 23,414 MiB, above the 8 GiB
reserve; disk free was 204 GiB. PLAN-040 acceptance and cleanup are complete.
