# PLAN-039 initial live inventory, November 12, 2026

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
Keep these identifiers with both verified snapshots until their backup
retention ends. To recover old provider data, use an isolated host and the
[documented restore procedure](../backup-and-recovery.md#named-data-store-recovery)
with the pinned implementation; reconcile the latest verified purge intent
before enabling access. Do not restore a pre-purge catalog into production as
live resources.

Source cleanup, a deployment of the narrowed API and UI, and deployed
retained-store checks remain. The sustained CPU/RAM comparison also remains
open. PLAN-039 is not complete.
