# Project retirement, restoration and complete purge

Status: implemented v1 behavior. Last reviewed November 15, 2026.

Every project has an immutable UUID. Its name can be reused only after
a complete purge succeeds; a new project receives a new UUID. Preview
tokens bind the name, UUID, observed versions, inventory and action
for 15 minutes. A stale preview returns a conflict and requires a
fresh preview.

## Endpoints and authority

Retirement URLs start with `/v1/projects/{project}`. Restore and purge
URLs start with `/v1/operator/projects/{project}`. Append these
suffixes:

| Action  | GET preview           | POST action | Authority      |
| ------- | --------------------- | ----------- | -------------- |
| Retire  | `/retirement-preview` | `/retire`   | Project retire |
| Restore | `/restore-preview`    | `/restore`  | Human admin    |
| Purge   | `/purge-preview`      | `/purge`    | Human admin    |

POST the exact `confirm_name`, `confirm_project_id` and `scope_token`
from the preview. All actions return 202 with `operation_id`, `kind`,
`state` and `status_url`. Poll `/v1/operations/{operation_id}`. A
repeated identical request joins active work. Active deployment or AI
work blocks acceptance; active lifecycle work prevents new project
changes and reserves the name durably.

The portal offers all three actions with scope preview and name
confirmation. The CLI exposes `retirement apply`,
`operator restore apply` and `operator purge apply`; consult
`devplat --help` for confirmation options and `--wait`.

## Retirement

Retirement removes the application namespace and public routes,
revokes project roles, automation credentials, hosted access and store
leases/bindings, and waits for credential revocation. The initiating
principal may still read its own retirement receipt with an otherwise
valid, unexpired token; this exception grants no further project
access. It retains provider data, declarations, revisions, operation
and audit history, AI records and existing telemetry until their
normal retention expires.

Before teardown, the API captures an authenticated encrypted recovery
point containing the desired declaration, application secrets, project
grants and recoverable access declarations. It uses a
purpose-separated key derived from `DATABASE_KEY` and binds ciphertext
to the project UUID. Preserve that key in recovery configuration.
Exported application declarations never expose secrets.

## Restoration

Restoration rebuilds the same UUID and name from the retained recovery
point. Missing retained stores cause a conflict; restoration never
substitutes an empty database. Version checks prevent silently
reinstating a binding whose owner changed it independently. The normal
deployment worker applies the retained declaration; the lifecycle
operation waits for apply completion and hosted access reconciliation.
Inspect application readiness separately.

Human project roles and recoverable hosted groups/policies are
restored. Old automation credentials, store leases, hosted credentials
and browser sessions remain invalid. Fresh credentials and session
epochs are generated. Automation identities need new issuance.
Independent human store grants and foreign consumers need renewed
approval; restoring the provider does not reconnect other projects
automatically.

Namespace/secret preparation is recorded once. Later reconciliation
preserves newly issued credentials. The encrypted recovery point is
deleted after a successful restoration.

## Complete purge

Purge may start from an active or retired project. It first retires
the project, then removes owned provider databases/buckets/instances,
access and credential records, desired/history/catalog data, AI
records, project audit entries and recovery points. Active foreign
store bindings or hosted consumers must be disconnected explicitly
before accepting the purge.

Audit erasure uses the privileged catalog connection inside the confirmed
purge transaction. A table write lock isolates the scoped deletion while its
append-only trigger is paused. The trigger is enabled again before commit;
transaction rollback also restores it. Ordinary audit writers retain no
update, delete or truncate authority.

A private root maintenance worker completes operational erasure. The
API has no Docker socket or backup credentials. Its signed handoff is
checked against the durable operation and immutable UUID before host
work begins.

The worker stops collection, removes kubelet log files for the retired
namespace and associated platform test reports, removes the UUID
tenant's Tempo blocks/WAL and pending scheduler jobs, and rebuilds
Loki from a complete export of the other tenants. Counts and hashes
verify retained log streams before the old shared WAL/index storage is
deleted. A truncated export blocks erasure. Prometheus deletion and
compaction produce a clean snapshot; rebuilding from it removes old
blocks, head and WAL. Store UUID series are included. Metrics are
cleaned again after catalog deletion so a final exporter scrape cannot
leave a project series behind.

These operations briefly interrupt shared telemetry services. A failed
log rebuild keeps the collector stopped and preserves the private
export and old volume for resumption. Inspect the blocked operation
and the maintenance service; do not delete its recovery files
manually.

After live catalog deletion, the worker takes and verifies a new full
backup for the remaining projects, then forgets and prunes every
managed snapshot whose ownership manifest contains the deleted UUID.
This can remove shared historical recovery points for other projects.
The new clean backup preserves their current recoverable state.
Repository checking must pass before completion. Historical snapshots
without ownership manifests are also removed because their ownership
cannot be certified. Unreadable snapshots block completion.

Completion waits for signed storage and final backup receipts. The
minimal completion record and handoff files expire after 24 hours.
Until final completion, the name stays reserved. A successful purge
cannot be restored. Managed deletion covers the configured platform
storage and backup repository; copies exported by users or records
held by external identity/model providers are outside that ownership
boundary.

## Maintenance and retry

Remote deployment installs `platform-project-purge.service` and its
timer. Local operators run the same worker as root from the
installation directory:

```bash
sudo python3 operations/maintenance/scripts/purge-project.py \
  --platform-dir /opt/developer-platform
```

A fresh installation with no managed backup configuration, service or
state has no offsite repository to clean; local temporary backup files
are removed. The default backup configuration is
`/etc/developer-platform/backup/job.json`. An existing backup
installation with missing credentials/configuration blocks completion.
See the
[maintenance implementation](../../operations/maintenance/README.md)
and [backup guide](backup-and-recovery.md).

Queued/running/blocked work survives API restarts. Provider or
maintenance failures leave the operation `blocked` for automatic
reconciliation. To retry a failed restored deployment after correcting
its cause, POST `/v1/operations/{operation_id}/retry` with `If-Match`
equal to the lifecycle operation's current `updated_at`. A stale
version returns 412. Retry preserves preparation and schedules a new
deployment when the preceding deployment failed.

S3 versioned backup repositories also require `s3:ListBucketVersions`
and `s3:DeleteObjectVersion` access for their dedicated prefix. After
restic pruning, maintenance erases noncurrent object versions and
delete markers, re-lists them, and checks the current repository
again. Object locks, retention policies or missing permissions leave
purge blocked. Only the current clean repository objects are retained;
historical copies of shared backup objects are removed. The
repository's local restic cache is also removed.
