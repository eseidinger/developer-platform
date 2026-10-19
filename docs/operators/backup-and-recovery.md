# Backup and Recovery

Status: current lab procedure with future capabilities explicitly labelled.

## Lab validation scope

[ADR-010](../architecture/decisions/ADR-010-single-environment-lab.md) selects the existing lab and watchdog for reversible operational exercises. [ADR-016](../architecture/decisions/ADR-016-phase-1a-recovery-scope.md) omits isolated recovery exercises from Phase 1A. Fresh-VM commands below document historical drills and the procedure for a future explicitly selected recovery; they are not a current Phase 1A acceptance step. Use the [in-place failure/freshness drills](../../operations/backup/README.md#start-with-the-playbooks) for current notification checks.

The accepted recovery-access procedure is to provision a fresh Ubuntu VM in WSL with the recovery-VM workflow when recovery is required. The Hetzner S3 access key and secret, and the restic repository password, are retained in the operator password manager outside `node-01` and outside this repository. Select an explicit verified snapshot, then run the recovery playbook against the new VM. This records the lab replacement-host plan; a restore drill remains separate evidence.

Before a deliberately selected restore, use the [read-only recovery failure preflight](../../operations/backup/README.md#read-only-recovery-failure-preflight) on that VM to confirm unavailable storage and invalid credential paths fail. It uses restic `--no-lock` and does not modify the repository. On September 28, 2026, the operator completed the unavailable-endpoint, wrong-password, and missing-password cases; all produced the expected failures and the non-secret report records no-lock mode. The operator may perform a lightweight snapshot/integrity review on the first Saturday of January, April, July, and October. A full restore requires a later explicit decision or an actual recovery event under ADR-016.

## Use the playbooks first

The supported path is the [backup and recovery playbook workflow](../../operations/backup/README.md#start-with-the-playbooks).
Run Ansible from WSL/the controller, using separate source and recovery inventories.

| Goal | Start here |
| --- | --- |
| Configure encrypted repository access | [setup-backup.yml](../../operations/backup/ansible/setup-backup.yml) |
| Deploy scheduled backups and independent alerts | [deploy-backup.yml](../../operations/backup/ansible/deploy-backup.yml) |
| Create a known record and take a verified backup | [prepare-recovery-test.yml](../../operations/backup/ansible/prepare-recovery-test.yml) |
| Restore a selected snapshot into a fresh VM and test it | [restore-recovery.yml](../../operations/backup/ansible/restore-recovery.yml) |

For a marker-based drill, run these from the repository root:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.yml \
  operations/backup/ansible/prepare-recovery-test.yml \
  -e recovery_test_project=smoke
```

Copy the resulting snapshot ID and independent marker path into the recovery
inventory. Prepare a [fresh recovery VM](../../operations/backup/README.md#local-recovery-vm-in-wsl-2),
then run:

```bash
ansible-playbook -i operations/backup/ansible/inventory.recovery.yml \
  operations/backup/ansible/restore-recovery.yml
```

See the [recovery playbook instructions](../../operations/backup/README.md#restore-a-fresh-recovery-vm-with-ansible)
for inventory creation, private credential prompts, host restrictions, and report
locations. Require `result: passed` and `historical_data_verified: true` for the
marker drill. Repeat acceptance checks with the
[prepared test script](../../operations/backup/README.md#run-tests-against-the-prepared-recovery-vm),
not by rerunning restoration over existing data.

## Evidence and limits

On September 26, 2026, the operator reported successful automated restoration of
snapshot `5ea9753aa32f362e351223154589489cf32b9188098da1f9d270030c1d39ed19`
into a fresh local Ubuntu VM. The marker-enabled suite passed bundle checksums,
platform readiness/catalog, project rollout, HTTP ingress, monitoring, Kubernetes
project database authentication/write/read, catalog CONNECT-privilege denial, and
verification of the independently recorded pre-backup SQL marker.

The earlier manual drill took an operator-estimated 30–60 minutes against a
four-hour RTO target; this is not a precisely timed automated recovery benchmark.
The selected RPO is 24 hours. Measure it against a recorded simulated failure time,
not the age of a backup at test completion. Public DNS/TLS recovery, live alert
receipt, unavailable backup and key failures, denied network destinations,
and database-backed application transactions remain separate acceptance work. Deliberate
corruption injection into the sole live repository is an accepted lab limitation under
[ADR-011](../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md); repository `check`,
verified readback, and checksum-rejection tests remain the available evidence.
The [delivery backlog progress checklist](../maintainers/delivery/backlog.md#current-backup-and-recovery-progress) owns task status;
this guide explains execution and the scope of reported evidence.

The following sections explain scope and manual fallback procedures. Use the
current in-place playbooks for routine notification drills; isolated restore procedures require a later explicit decision or an actual recovery event under ADR-016.

The automated playbooks and `test-recovery.py check` path above still assume the
historical `project_<name>` database and project-wide `database` Secret.
For a named PostgreSQL resource, use the helper's
[quarantined SQL marker check](../../operations/backup/README.md#verify-a-named-postgresql-marker)
to verify restored data without releasing access. The current
restore script has named-store volume/quarantine support, but refuses automatic
reapply of recovered bound components until fresh approval and declarations.
Use the [named-store recovery procedure](#named-data-store-recovery); a complete
deployed off-host restore/reconnection remains open.

## Current backup scope

| Data | Current mechanism | Remaining responsibility |
| --- | --- | --- |
| Project databases, roles and password hashes | Compressed `pg_dumpall` in encrypted restic bundle | Verify pre-backup data and application recovery |
| Platform metadata and identity | Full SQL dump includes catalog, revisions, operations, grants, audit, hosted-access/store/AI records and Keycloak's separate database | Restore authorization under quarantine; review current administrative authority |
| `.env`, especially `DATABASE_KEY` and `POSTGRES_PASSWORD` | Deployment archive in encrypted bundle | Retain repository credentials/password independently of the host |
| Caddy data/config and customized Grafana state | Stopped-service volume archives in encrypted bundle | Validate restored settings; disable production notifications in recovery |
| Infrastructure, alert rules, workload image identities | Deployed sources/config in the encrypted bundle plus image metadata; images are not exported | Retain compatible images and record versions/digests |
| Application Secrets | `project-secrets.json` captures current managed `app-secrets` values | Restore through the controlled path; prior rotation values are excluded |
| Named-store data and recovery intent | SQL resource databases, retained native volumes, Neo4j image/volume inventory and `store-recovery.json` | Validate provider archives, latest verified intent, quarantine and fresh grants/bindings |
| External watchdog MySQL/configuration | Separate hosting service | Back up through the hosting provider; PostgreSQL dump excludes it |

The workload contract has no PVCs; durable data belongs in explicitly bound
named resources. The source bundle includes generated operator store configuration
under `.runtime/stores` when present. Telemetry stores and disposable pgAdmin
preferences are not a substitute for application data/credential backups; Tempo's
bounded filesystem is outside the backup.

The implemented bundle, verification, retention and notification boundaries are recorded in [ADR-015](../architecture/decisions/ADR-015-verified-backup-bundles.md). Readback validates captured bytes; it does not establish SQL/application restoration.

## Set up encrypted off-host storage

Hosted-access catalogs in newer bundles are quarantined by the isolated restore
script before services start. A human platform administrator must explicitly
run the [hosted-access recovery flow](identity-and-access.md#hosted-application-access-installation-and-recovery)
to invalidate browser sessions, rotate uncertain service credentials, and
reconcile approved membership outward before application routes activate.
This safeguard does not establish the full deployed hosted-access recovery
gate; that remains PLAN-019 acceptance work.

Use the [backup repository playbook](../../operations/backup/README.md#encrypted-s3-backup-repository-setup)
to install restic, configure private S3 credentials and a separately recoverable
repository password, and explicitly initialize a new repository when needed.
This prepares storage only. The separate [scheduled backup playbook](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts)
adds capture, exact-snapshot readback, retention and independent backup alerts;
successful-path restore has operator-reported evidence; remaining acceptance is described above. The confirmed policy and
implementation evidence are tracked under OPS-006 in the
[delivery backlog](../maintainers/delivery/backlog.md).

## Make a current backup

For a drill, prefer [prepare-recovery-test.yml](../../operations/backup/ansible/prepare-recovery-test.yml), which seeds a marker, runs backup and saves evidence. For an ordinary backup without adding a marker, use the following manual trigger.

After completing [backup deployment](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts), start the managed backup service on the source host:

```bash
sudo systemctl start platform-backup.service
sudo cat /var/lib/developer-platform-backup/status.json
sudo journalctl -u platform-backup.service -n 40 --no-pager
sudo /usr/local/sbin/platform-restic snapshots --host node-01 --tag developer-platform,verified
```

The service captures PostgreSQL roles/databases, deployment configuration, and service data; encrypts and uploads the bundle; verifies an exact-snapshot readback; and applies retention. Caddy and Grafana briefly stop during capture. Native-store bundles additionally
pause managed leases and stop selected native services/Neo4j instances while
capturing their retained volumes; PostgreSQL-only capture uses the existing online
logical dump. The bounded 35-minute lease pause, restart recovery and limits are
in [store backup semantics](data-stores.md#retention-and-capacity). Starting an already-running service does not create another backup.

Confirm `result: success`, a recent capture timestamp, and the matching verified snapshot. Record its full identifier and source revision. Notification delivery can remain pending even after a verified backup; inspect the journal and status before retrying.

Follow [bundle retrieval](#retrieve-a-scheduled-recovery-bundle) to obtain the verified `postgres.sql.gz` and original `.env` for an isolated restore. Preserve the original `DATABASE_KEY`: generating a replacement produces credentials that do not match restored roles. Coordinate application writes if consistency across databases is required; the dump does not provide a single cross-database application transaction snapshot.

## Restore into an isolated installation

Select an explicit verified snapshot and a fresh host under the recovery scope
above. Use `restore-recovery.yml` with its separate protected inventory. A second
checkout or Compose project on the source host is insufficient isolation because
cluster names, Docker networks and ports are fixed.

The script verifies bundle hashes, requires empty target volumes and compatible
provider/image inventory, restores SQL and native archives, and sets hosted-access
and named-store quarantine before starting services. It reads the latest verified
store intent independently of the chosen data snapshot, revokes recovered grants
and credentials, replays purge tombstones and validates surviving data. Preserve
all operator keys from the original encrypted configuration. Never clear recovery
guards manually or use an old data snapshot to reactivate revoked access.

The automated marker/test path retains the earlier implicit-database assumptions
described above. The separate named PostgreSQL marker path checks catalog and SQL
data under quarantine; it is not application reconnection acceptance.
Current local provider restore fixtures are documented in
[data-store operations](data-stores.md) and the
[upgrade runbook](runbooks/store-upgrades.md). A deployed full restore still needs
separate application data, authorization, reconnection and RPO/RTO evidence.

## Reapply restored projects

Bootstrap creates cluster/controller resources but does not replay all stored
workloads automatically. Reapply each reviewed public declaration from the
application's versioned deployment source. `GET /projects` returns internal
normalized specifications, including resolved-image/runtime fields; copying those
objects directly back to `PUT /projects/{name}` is not a supported declaration
export and can return 422.

For a full store restore, first complete quarantine reconciliation, obtain fresh
owner approval for the consuming component, and update the declaration with its
new binding UUID. Retain the restored data in the independent resource. Inspect
empty and retired projects separately; do not blindly deploy `spec: null` or
reactivate retired projects. Review original image digests, configuration,
scheduled jobs and external side effects before reapplying.

From a trusted shell with a fresh authorized human CLI session:

```bash
devplat projects list --output json
devplat stores list --project orders --output json
# Review application.json and its new approved binding IDs first.
devplat deploy apply --project orders --file application.json --wait --output json
devplat components list --project orders --output json
```

Use actual project names and declarations. Restore current write-only application
Secrets from the protected bundle using the controlled recovery path before
accepting application readiness; secret values are absent from revisions and
ordinary API reads. Reconcile hosted access using the separate
[human-admin recovery action](identity-and-access.md#hosted-application-access-installation-and-recovery)
and verify authorizer readiness before opening traffic.

The automated restore script's selected-project replay still submits stored
internal specs and refuses recovered bindings. It does not provide a complete
automatic `v1alpha2` declaration export/fresh-binding workflow. Keep that
implementation gap explicit when planning recovery; do not interpret SQL restore
or an unbound echo rollout as store-backed application recovery.

## Recovery verification and evidence

The [recovery playbook](../../operations/backup/ansible/restore-recovery.yml) runs the acceptance suite and fetches its reports. For repeat checks, use [test-recovery.py](../../operations/backup/scripts/test-recovery.py); supplementary manual checks follow.

For each project, use the [runbook](runbooks/application.md#application-unhealthy-after-deployment) to inspect rollout and routing, then execute the application's own data checks. For `hello`, for example:

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello rollout status deployment/hello --timeout=180s
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

The echo example does not exercise PostgreSQL. Use a database-backed application with known pre-backup records: verify those records survived, then write and read a new record through the application. Verify database ownership, login permissions, and denied foreign-project access. Preserve private import logs and record source/target environments, code/image versions, backup ID/checksum, start/end times, data checks, errors, and measured recovery point/duration. The reported SQL-marker drill above does not replace application-specific transaction checks.

A production routing switch is a separate operational step after acceptance. Restore intended domains and reapply specs before changing DNS; validate TLS, application data, monitoring, and watchdog down/recovery receipt. Do not point production traffic at an unverified exercise host.

## Target recovery capabilities

Encrypted off-host backup automation and independent backup-age alerts are
implemented. The selected RPO is 24 hours and RTO four hours for node-01;
historical marker recovery and selected notification paths have recorded evidence.
Identity, revisions, durable operations, store/access catalogs and purge intent
are captured now. Recovery must quarantine worker-driven access and review current
authority before traffic resumes. Precise recovery measurement and deployed
store-backed application reconnection remain open.

See [Deployment](lifecycle.md), [Runbook](runbooks/README.md), and [ADR-003](../architecture/decisions/ADR-003-postgresql-provisioning.md).


## Retrieve a scheduled recovery bundle

The [recovery playbook](../../operations/backup/ansible/restore-recovery.yml) retrieves and verifies the explicitly selected snapshot. Use the commands below for manual inspection or recovery outside the playbook.

Use an isolated recovery host with restic, S3 credentials and the independently
saved repository password configured. Identify an explicit verified snapshot:

```bash
sudo /usr/local/sbin/platform-restic snapshots --host node-01 --tag developer-platform,verified
sudo /usr/local/sbin/platform-restic restore REPLACE_WITH_FULL_SNAPSHOT_ID --target /root/platform-recovery
```

Use a new empty destination. The restored tree contains `bundle/manifest.json`
(with its original directory hierarchy as recorded by restic). Verify every listed
SHA-256 checksum before using `postgres.sql.gz` or the archives. Keep the entire
extracted tree private: it contains credentials. Inspect archive members and
extract only into the isolated recovery environment, never over the source host.

`platform-files.tar.gz` contains the deployment source and `.env`;
`host-config.tar.gz` contains private host configuration and units. Service-state
archives are `proxy-data.tar.gz`, `proxy-config.tar.gz`, and `grafana-grafana.tar.gz`.
Restore them into their corresponding freshly created named volumes while those
services are stopped, preserving ownership. Adapt test domains/notification
identities before starting services; never send recovery-test signals to the
production watchdog channel. Then follow the isolated SQL import/reapply procedure
above, verify data markers, permissions, ingress and alerts, and measure RPO/RTO.
The backup job's automatic readback validates bytes, not these application outcomes.

## Named data-store recovery

Named-store purge intent is now part of each verified bundle as
`store-recovery.json`. A pending purge cannot delete provider data until this
intent has been encrypted, uploaded and read-back verified; the backup job then
acknowledges the exact resource/version/snapshot. Deploy the updated backup job
with the store implementation. The schedule and retained backup copies keep their
existing policy.

A named-store restore stays quarantined until current resource dispositions are
read from the **latest verified** off-host bundle, independently of the selected
data snapshot. Recovered grants and credentials are revoked; purge tombstones
are replayed before access is enabled. Fresh owner approval/new component bindings
are required afterward. AGE recovery additionally requires authoritative graph
rebuild and Cypher validation. See the [named-store operator workflow](data-stores.md).
Local encrypted intent fixtures are not a complete deployed recovery or RTO test.
