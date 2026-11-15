# Installed v1 acceptance, November 15, 2026

This records the actual reset, deployment and lifecycle acceptance on
`node-01.eseidinger.de`. The API uses `https://platform.eseidinger.de/v1`, the
portal uses the platform origin, and human login uses
`https://identity.eseidinger.de`.

The installed application and maintenance changes are committed through
`9a2a64f`. The primary Ansible deployment completed with 39 successful tasks,
zero failures and zero unreachable hosts. Subsequent focused API-image and
maintenance updates contain the acceptance fixes described below. The private
installation record records the actual revision and image references.

## Reset and deployment

- Removed all 38 old projects by resetting the workload cluster, platform
  volumes, trace storage and project runtime records.
- Removed all 23 old offsite snapshots and all 376 objects/versions found in
  the dedicated backup repository prefix. Reinitialized an empty repository.
- Removed old local database backups and all three local recovery VM datasets.
- Preserved human identities and operational credentials. Removed 19
  project-specific identity clients and old identity groups. The temporary
  identity database transfer was deleted after restoration.
- Built the complete production image, including the portal and pinned store
  console. Installed the purge systemd service and timer and refreshed the
  installed backup runner.
- Removed the one-time administrator bootstrap setting and recreated the API.

ADRs and existing plans remain under [history](../../history/README.md).

## Automated checks

| Check                                      | Result                   |
| ------------------------------------------ | ------------------------ |
| API, PostgreSQL, Keycloak and proxy tests  | 540 passed, none skipped |
| CLI unit tests                             | 45 passed                |
| UI unit tests                              | 61 passed                |
| UI build-script tests                      | 2 passed                 |
| Browser regression tests                   | 34 passed                |
| Platform helpers, including real SQL tests | 96 passed, none skipped  |
| Ansible helper and archive tests           | 31 passed                |
| Backup tests with real encrypted restic    | 62 passed, none skipped  |
| Host purge maintenance tests               | 6 passed                 |

Relevant Python, YAML, Ansible and UI lint/format checks pass. API contract,
type checking, UI production build, full Docker image build and API/CLI 1.0.0
package builds pass. The earlier
[repository and native-backend baseline](v1-contract-2026-11-15.md) records the
additional script and isolated telemetry checks.

## Installed lifecycle checks

Two independent test projects received an application, PostgreSQL and versioned
S3 resources, component bindings, write-only application secrets, and distinct
data and telemetry markers.

- Normal OIDC login succeeded through the API/CLI flow and the deployed portal.
- CLI 1.0.0 listed projects, exported the v1 Application, inspected restore
  scope, accepted confirmed retirement and polled it to completion.
- The deployed portal created and deployed an application, checked runtime
  readiness, and completed repeated retire/restore cycles without runtime
  errors. Rapidly reopening cached lifecycle dialogs used refreshed scopes.
- The portal also followed a complete project purge through its final backup
  receipt and returned to the project list without browser runtime errors.
- Public component hostnames completed verified TLS and enforced the expected
  default-deny behavior without an active hosted-access policy. Operation
  results reported the generated component hostname.
- Retirement revoked a still-unexpired CI token and the old native PostgreSQL
  and S3 credentials. The provider data remained readable to the operator.
- Restoration preserved the project UUID, PostgreSQL/S3 markers and all user
  secrets, including `ACCESS_TOKEN`. Managed store credentials changed and the
  old credentials remained unusable.
- Stopping RustFS blocked restore. The durable operation survived an API
  restart, accepted a version-bound retry using its public UTC timestamp, and
  succeeded after the store returned.
- A foreign store consumer prevented purge acceptance. Explicitly disconnecting
  it removed the blocker. A CI identity could not obtain purge authority.

## Complete purge and backups

Before purging, a new full offsite backup was created, restored for verification
and checked. Its manifest contained all three acceptance projects.

The primary purge completed with all three receipt flags true:
`live_resources_removed`, `operational_data_removed` and `backups_removed`.
Independent checks verified that its database and bucket were absent and its
Loki, Tempo and Prometheus markers were gone. The control project's data and
all three telemetry markers remained present. Tempo's missing-trace response
was checked for empty contents rather than relying on HTTP status alone.

The original verified snapshot was absent from the repository after purge.
Every remaining manifest excluded the deleted UUID. The repository contained
one newly verified clean snapshot at that checkpoint. Maintenance also checked
the repository after pruning and historical S3-version cleanup.

The name remained reserved after catalog deletion while backup cleanup was
pending. Reusing it after successful completion allocated a different UUID.
Ordinary audit deletion remained prohibited after the scoped privileged purge;
SQL regression tests also verified guard restoration on an injected failure.

See the [lifecycle runbook](../project-lifecycle.md) for authority, confirmation,
retry behavior, managed-erasure boundaries and the 24-hour completion receipt.

## Final installation state

All four acceptance project identities, including the reused name, completed
purge. The public API and CLI return an empty project list. There are no pending
lifecycle operations, project stores, grants, credentials, recovery points,
application revisions/operations, hosted-access resources or AI records. No
resource databases, resource/login roles, resource buckets or test CI clients
remain. The append-only audit trigger is enabled.

Both data-bearing projects' Loki, Tempo and Prometheus markers are absent when
queried over a 24-hour interval or by trace identity. The final two verified
offsite snapshots have empty project-ownership manifests; no historical object
versions or delete markers remain in the repository prefix. Backup work and
recovery-intent directories are absent, and notification delivery is complete.

The common API-based runtime images were rebuilt from the final code and
reconciled successfully. Every platform service is running, configured health
checks pass, public readiness and normal human authorization succeed, and the
backup, backup-notification, purge and heartbeat timers are active. Temporary
operator credential copies and disposable local integration containers were
removed.

## Acceptance fixes

The real installation exposed and resolved missing maintenance sources in the
deployment archive, absent lifecycle tables in integration fixtures, UTC
timestamp round-tripping on retry, overly broad recovery-secret filtering,
cached UI confirmations, incorrect reported application hosts, the k3d load
balancer being scanned for pod logs, an unbounded Loki verification interval,
and the production append-only audit trigger blocking confirmed purge.

The stored purge operation resumed through these corrections. Retained log
exports and retry state were preserved until their verification succeeded.
