# PLAN-039 inventory, cutover, and validation, November 12, 2026

Initial read-only observation of `node-01.eseidinger.de` at approximately
15:35 UTC.
The deployed source revision could not be read because
`/opt/developer-platform` is not a Git checkout. No deployment, resource
mutation, or service shutdown was performed during this initial inventory.
The running API container image ID was
`sha256:4bb09e1a5c84c04d8dac7547d1c0bd4968a445678bd907329596981daeee4541`.

## Catalog and access

The control database reported these non-PostgreSQL/S3 resource counts:

| Provider   | Retired and observed retired | Purged and observed purged |
| ---------- | ---------------------------- | -------------------------- |
| CouchDB    | 5                            | 0                          |
| HugeGraph  | 2                            | 0                          |
| Neo4j      | 1                            | 4                          |
| OpenSearch | 2                            | 3                          |
| Qdrant     | 1                            | 2                          |

All 11 unpurged resources had zero pending or active grants and zero unexpired,
non-revoked credentials in the catalog query. This establishes neither data
ownership nor purge eligibility. The retained stores had four active
PostgreSQL resources and one active S3 resource. A resource-by-resource owner,
application, data classification, backup-retention, and migration disposition
record is still required. The inventory must also cover native data, routes,
secrets, and backups before provider shutdown.

The selected Compose profiles were `s3,qdrant,opensearch,neo4j,couchdb,hugegraph`.
All five removed shared provider services remained running, as did OpenSearch
Dashboards and the Neo4j controller. The corresponding Compose volumes were
still present. No dedicated Neo4j instance container appeared in the running
container list. A verified Restic snapshot was listed at
2026-11-12 12:03:36 UTC; its contents and coverage of each resource have not
been checked. `store_control.backup_until` was empty, and recovery quarantine
was false. These observations do not satisfy the per-resource backup gate.

## Capacity point sample

At 15:35 UTC the host reported 16 CPUs, 31,337 MiB RAM, and 20,610 MiB
available memory. The six running legacy-provider support containers below
had these Docker limits and one `docker stats --no-stream` sample:

| Container             | CPU limit | RAM limit | Sampled memory |
| --------------------- | --------- | --------- | -------------- |
| Neo4j controller      | 0.25 CPU  | 128 MiB   | 61.85 MiB      |
| OpenSearch Dashboards | 0.5 CPU   | 512 MiB   | 234.5 MiB      |
| Qdrant                | 0.5 CPU   | 512 MiB   | 18.19 MiB      |
| CouchDB               | 0.5 CPU   | 768 MiB   | 99.29 MiB      |
| HugeGraph             | 1 CPU     | 1.5 GiB   | 542.4 MiB      |
| OpenSearch            | 1 CPU     | 1.5 GiB   | 958.5 MiB      |

The limits total 3.75 CPUs and 4,992 MiB; sampled container memory totals
approximately 1,915 MiB. Limits are ceilings, not guaranteed reservations.
After the six services stopped, host available memory was 22,571 MiB, compared
with 20,610 MiB in the initial point sample. The 1,961 MiB difference is
consistent with the container sample, but workload and cache state were not
controlled. Record comparable workload and telemetry time series before
claiming a sustained capacity gain.

## Purge and service record

The data owner confirmed that all 11 resources were disposable test data and
authorized deletion after backup verification. The verified snapshot
`3d290a2af403e55b9ce06498ace62b999add0612ce7be0755a802a0676813370`
contained all 11 resources with matching IDs, owners, names, versions, and
retired states. It also contained the provider archives and catalog manifest.
The supported API accepted 11 exact purge previews and requests. A manually
started backup then verified snapshot
`c2f29211644a8e68f5d6ebdf7a4fc6f419490b2bbc09aceb408b7dffaf35c6ce`.
Its recovery manifest contains all 11 `purging` identities and next versions.
The worker reported all 11 `purged/purged`, each with that snapshot ID and the
matching purge version. Existing catalog tombstones and audit history remain.

The six legacy support containers were stopped with `docker compose stop`.
PostgreSQL, RustFS, API, and store-access relay remained healthy. The remote
`.env` now selects only `s3` and allocates capacity only to PostgreSQL and S3;
a private copy of the prior `.env` remains at
`/opt/developer-platform/.runtime/plan039-env-before.env` for rollback.
The seven legacy service containers, six named provider volumes, and the
inventoried anonymous HugeGraph volume were subsequently removed. Remote
`shared-stores.yaml` now defines only RustFS, and `docker compose config`
contains no removed-provider services. The temporary API test-runner
credential was revoked and its private secret file deleted.

## Version-pinned recovery and remaining gates

The pre-removal provider implementation is available at Git commit `632b921`;
the deployed API image ID before cleanup was
`sha256:4bb09e1a5c84c04d8dac7547d1c0bd4968a445678bd907329596981daeee4541`.
The identifiers remain in this record. Normal Restic retention later pruned
the two same-day snapshots `3d290a2a` and `c2f29211` after a newer verified
backup; older daily snapshots remain available. The purged test data is not
assumed recoverable from the latest snapshot. To recover old provider data, use
an isolated host and the
[documented restore procedure](../backup-and-recovery.md#named-data-store-recovery)
with the pinned implementation; reconcile the latest verified purge intent
before enabling access. Do not restore a pre-purge catalog into production as
live resources.

## Committed rollout and retained-store checks

Commit `769843587ecb0c5033f40896cca4d575e4976e9d` was deployed through
`ansible/deploy.yml`; the installation record reports that exact clean revision.
Ansible completed with 35 successful tasks and no failures. The host's Compose
service list contains PostgreSQL and RustFS as its only project data stores.
All remaining Compose containers were running and healthy where they expose a
health check; `/readyz` returned `ready`. Obsolete OpenSearch private runtime
files and temporary rollback configuration copies were removed after the
verified rollout. The live `.env` has no removed-provider secret assignments.

The authenticated API context advertised exactly `postgresql` and `s3`, both
enabled. Direct create calls for each of OpenSearch, Qdrant, Neo4j, CouchDB, and
HugeGraph returned HTTP 422; a catalog count confirmed no inserted probe row.
A disposable PostgreSQL resource with `vector` and a disposable S3 resource
reached `active/active`. SQL confirmed `vector` installed in the new database;
an S3 HEAD confirmed the new bucket. The S3 worker initially reported
`ProviderOperationFailed` during rollout, then an idempotent provision retry
succeeded and the worker reported `active/active`. Both resources reached
`retired/retired` through the API. Exact purge requests were acknowledged only
after the successful encrypted backup snapshot
`faf78d33a0edbbe15ab21dc28df05dc889a857336d052857938f1f11ad2c2c25`.
Both ended `purged/purged` with matching backup and resource versions. The test
database was absent and the test bucket returned HTTP 404. The short-lived
verification client was revoked and its secret file deleted. The retained
original four active PostgreSQL resources and one active S3 resource remained.

Prometheus reported `platform_native_collection_up{provider="postgresql"}=1`,
`platform_native_selected=1` for PostgreSQL and S3 only, RustFS native readiness
`1`, and no firing `NativeStoreCollectionUnavailable` alert. Application unit,
local console/relay, CLI, backup, UI, Compose, Ansible, and documentation checks
passed. The local application suite ran 511 tests with 14 skips. A new deployed
interactive human console session was not issued because the verification client
was a service account; the retained S3 console passed its local gateway tests.

## Paired CPU and RAM comparison

Prometheus `query_range` sampled each series once per minute over equal
15-minute steady windows: 15:15–15:30 UTC with legacy services running, and
16:25–16:40 UTC after their removal but before the new application deployment.
Both windows used the same host exporter, telemetry configuration, and workload
placement. The 16 observations per series gave these means:

| Metric                        |      Before |       After |       Change |
| ----------------------------- | ----------: | ----------: | -----------: |
| Host available memory         |  20,644 MiB |  22,653 MiB |   +2,009 MiB |
| Host non-idle, non-iowait CPU | 1.348 cores | 1.043 cores | -0.305 cores |
| Project workload CPU usage    | 0.011 cores | 0.011 cores |    unchanged |
| Pod CPU requests              |  5.05 cores |  5.05 cores |    unchanged |
| Pod memory requests           |   5,471 MiB |   5,471 MiB |    unchanged |

The removed Docker limits total 3.75 CPUs and 4,992 MiB RAM; these are ceilings,
not guaranteed reservations. The initial point sample showed about 1,915 MiB
actual memory in those containers, consistent with the 2,009 MiB increase in
host available memory. The same 12-minute windows around verified backups at
12:03 and 17:03 UTC showed available-memory means of 20,743 and 22,798 MiB,
respectively, but backup pauses caused scrape gaps and the later window also
included rollout/test work. They support the direction of the steady result,
not a controlled backup-throughput comparison. This establishes reclaimed
capacity at the observed light workload; peak throughput and extension load
belong to subsequent capacity work.
