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

Before deployment, confirm
the pinned image and extension files on a disposable restore server, then run
the controlled upgrade and rollback rehearsal. Check existing AGE and pgvector resources,
new time-series/spatial/queue/analytics resources, roles and credential
revocation, monitored extension presence, host reserve, and application
reconnection. Keep PLAN-040 open until the deployed checks and capacity budget
are recorded.
