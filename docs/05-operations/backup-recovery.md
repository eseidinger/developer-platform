# Backup and Recovery

## Lab validation scope

[ADR-010](../03-decisions/ADR-010-single-environment-lab.md) selects the existing lab and watchdog for reversible operational exercises. [ADR-016](../03-decisions/ADR-016-phase-1a-recovery-scope.md) omits isolated recovery exercises from Phase 1A. Fresh-VM commands below document historical drills and the procedure for a future explicitly selected recovery; they are not a current Phase 1A acceptance step. Use the [in-place failure/freshness drills](../../operations/backup/README.md#start-with-the-playbooks) for current notification checks.

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
[ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md); repository `check`,
verified readback, and checksum-rejection tests remain the available evidence.
The [delivery backlog progress checklist](../04-development/delivery-backlog.md#current-backup-and-recovery-progress) owns task status;
this guide explains execution and the scope of reported evidence.

The following sections explain scope and manual fallback procedures. Use the
current in-place playbooks for routine notification drills; isolated restore procedures require a later explicit decision or an actual recovery event under ADR-016.

## Current backup scope

| Data | Current mechanism | Remaining responsibility |
| --- | --- | --- |
| Project databases, roles and password hashes | Compressed `pg_dumpall` in encrypted restic bundle | Verify pre-backup data and application recovery |
| Platform metadata | Same dump includes `platform.projects` with latest specs/status | No revision history, jobs, or audit records exist |
| `.env`, especially `DATABASE_KEY` and `POSTGRES_PASSWORD` | Deployment archive in encrypted bundle | Retain repository credentials/password independently of the host |
| Caddy data/config and customized Grafana state | Stopped-service volume archives in encrypted bundle | Validate restored settings; disable production notifications in recovery |
| Infrastructure, alert rules, workload image identities | Deployed sources/config in the encrypted bundle plus image metadata; images are not exported | Retain compatible images and record versions/digests |
| External watchdog MySQL/configuration | Separate hosting service | Back up through the hosting provider; PostgreSQL dump excludes it |

The workload contract has no PVCs; durable application data belongs in PostgreSQL. Identity-provider state, job/revision metadata, and retained-resource inventories belong to the target architecture and are not current backup artifacts.

The implemented bundle, verification, retention and notification boundaries are recorded in [ADR-015](../03-decisions/ADR-015-verified-backup-bundles.md). Readback validates captured bytes; it does not establish SQL/application restoration.

## Set up encrypted off-host storage

Use the [backup repository playbook](../../operations/backup/README.md#encrypted-s3-backup-repository-setup)
to install restic, configure private S3 credentials and a separately recoverable
repository password, and explicitly initialize a new repository when needed.
This prepares storage only. The separate [scheduled backup playbook](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts)
adds capture, exact-snapshot readback, retention and independent backup alerts;
successful-path restore has operator-reported evidence; remaining acceptance is described above. The confirmed policy and
implementation evidence are tracked under OPS-006 in the
[delivery backlog](../04-development/delivery-backlog.md).

## Make a current backup

For a drill, prefer [prepare-recovery-test.yml](../../operations/backup/ansible/prepare-recovery-test.yml), which seeds a marker, runs backup and saves evidence. For an ordinary backup without adding a marker, use the following manual trigger.

After completing [backup deployment](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts), start the managed backup service on the source host:

```bash
sudo systemctl start platform-backup.service
sudo cat /var/lib/developer-platform-backup/status.json
sudo journalctl -u platform-backup.service -n 40 --no-pager
sudo /usr/local/sbin/platform-restic snapshots --host node-01 --tag developer-platform,verified
```

The service captures PostgreSQL roles/databases, deployment configuration, and service data; encrypts and uploads the bundle; verifies an exact-snapshot readback; and applies retention. Caddy and Grafana briefly stop during capture. Starting an already-running service does not create another backup.

Confirm `result: success`, a recent capture timestamp, and the matching verified snapshot. Record its full identifier and source revision. Notification delivery can remain pending even after a verified backup; inspect the journal and status before retrying.

Follow [bundle retrieval](#retrieve-a-scheduled-recovery-bundle) to obtain the verified `postgres.sql.gz` and original `.env` for an isolated restore. Preserve the original `DATABASE_KEY`: generating a replacement produces credentials that do not match restored roles. Coordinate application writes if consistency across databases is required; the dump does not provide a single cross-database application transaction snapshot.

## Restore into an isolated installation

Prefer [restore-recovery.yml](../../operations/backup/ansible/restore-recovery.yml) on a fresh recovery VM. The manual fallback below explains the underlying steps for diagnosis and environments outside that playbook’s supported scope.

Use a separate host or Docker daemon with no existing platform data. A different checkout or Compose project name on the source host is insufficient isolation: the Docker network, k3d cluster name, and host ports are fixed. This is a whole-instance restore, not a procedure for overwriting one project in an active installation.

1. Install the prerequisites from [deployment](deployment.md). Check out the recorded source revision and use the same PostgreSQL major version for the first exercise; validate any version migration separately. Restore the original `.env` securely with mode 0600 and make the verified, decrypted dump available privately.
2. Keep the recovery host isolated from production routing and external application side effects. Set `EDGE_BIND_IP=127.0.0.1`, `PLATFORM_DOMAIN=platform.localhost`, and `APPS_DOMAIN=apps.localhost` in its `.env`. Preserve `DATABASE_KEY` and `POSTGRES_PASSWORD`. Use a fresh shell with no old exported platform settings. Do not enable a sender that would impersonate the production heartbeat.
3. From the recovery checkout, validate configuration and start only PostgreSQL:

```bash
docker compose config --quiet
docker compose up -d --wait --wait-timeout 120 postgres
```

Confirm this is the empty recovery instance before proceeding. Only the initialized `postgres`/`platform` and template databases should exist; no project data should already be present:

```bash
docker compose exec -T postgres psql -X -U postgres -d postgres -c '\l'
```

4. Import the selected dump, keeping private logs for review:

```bash
set -o pipefail
umask 077
mkdir -p .runtime/recovery
backup_file=/absolute/private/path/bundle/postgres.sql.gz
gzip -t "$backup_file" && gzip -dc "$backup_file" | \
  docker compose exec -T postgres psql -X -U postgres -d postgres \
  > .runtime/recovery/restore.stdout 2> .runtime/recovery/restore.stderr
```

Replace the path before execution. The stock PostgreSQL container has already created the `postgres` role and `platform` database, so this archived full-dump approach can report duplicate-object errors for those initialization objects. It intentionally does not use `ON_ERROR_STOP`, which would stop at the expected duplicates. **A zero exit code is not import acceptance:** inspect both logs, account for every error, and verify all databases/roles/data. Do not blanket-ignore duplicate errors for project objects; they indicate a non-empty target or another problem. Logs can contain SQL and sensitive values; keep them private. If unexpected errors occur, stop and correct the recovery procedure in a fresh isolated target rather than importing repeatedly over partial state.

5. Check that the recovery catalog is readable:

```bash
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U postgres -d platform \
  -c 'SELECT name, spec, status FROM projects ORDER BY name;'
```

A missing catalog table is a recovery problem unless the backed-up installation had never initialized the API. Review expected database names, ownership, and roles against the source inventory. The dump may restore the administrator password, so `.env` must match the original credentials before the API starts.

6. Bootstrap the cluster and services, then reapply the catalog as below:

```bash
python3 scripts/install-k3d.py
bash scripts/up.sh
curl --fail-with-body http://127.0.0.1:8000/readyz
```

The API has no background workload reconciler. Bootstrap recreates cluster/controller credentials, but does not restore application workloads until PUT is repeated.

## Reapply restored projects

The [recovery playbook](../../operations/backup/ansible/restore-recovery.yml) reapplies explicitly selected projects automatically. The following is a manual fallback.

Use this after SQL restore, or after cluster recreation with intact PostgreSQL volumes. The following commands target only the local API. They apply every non-retired stored project's latest spec, so review the catalog before running the Python block and ensure this is the intended recovery installation.

```bash
umask 077
mkdir -p .runtime/recovery
eval "$(python3 scripts/env.py)"
curl --fail-with-body http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer $PLATFORM_TOKEN" \
  --output .runtime/recovery/projects.json
```

Review `.runtime/recovery/projects.json` for expected names, images, and ports. It is an external copy of the latest catalog, not a revision history. Then reapply:

```bash
python3 - <<'PYTHON'
import json
import os
import re
import urllib.request
from pathlib import Path

projects = json.loads(Path('.runtime/recovery/projects.json').read_text())
projects = [project for project in projects if project.get('status') != 'retired']
for project in projects:
    name = project['name']
    if (not isinstance(name, str)
            or not re.fullmatch(r'[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?', name)
            or project['spec']['name'] != name):
        raise ValueError('Invalid project identity in recovery catalog')
for project in projects:
    name = project['name']
    request = urllib.request.Request(
        'http://127.0.0.1:8000/projects/' + name,
        data=json.dumps(project['spec']).encode(),
        headers={'Authorization': 'Bearer ' + os.environ['PLATFORM_TOKEN'],
                 'Content-Type': 'application/json'},
        method='PUT',
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    if result.get('status') != 'applied':
        raise RuntimeError('Unexpected provisioning result for ' + name)
    print(name + ': applied; rollout and data verification still required')
PYTHON
```

An error stops the loop. Earlier projects may already have been applied; inspect status/resources, fix the cause, and repeat safely with the same specs. A timeout does not prove the server stopped processing. Project passwords are derived from the restored `DATABASE_KEY`; provisioning does not reset existing role passwords.

## Recovery verification and evidence

The [recovery playbook](../../operations/backup/ansible/restore-recovery.yml) runs the acceptance suite and fetches its reports. For repeat checks, use [test-recovery.py](../../operations/backup/scripts/test-recovery.py); supplementary manual checks follow.

For each project, use the [runbook](runbook.md#application-unhealthy-after-deployment) to inspect rollout and routing, then execute the application's own data checks. For `hello`, for example:

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello rollout status deployment/hello --timeout=180s
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

The echo example does not exercise PostgreSQL. Use a database-backed application with known pre-backup records: verify those records survived, then write and read a new record through the application. Verify database ownership, login permissions, and denied foreign-project access. Preserve private import logs and record source/target environments, code/image versions, backup ID/checksum, start/end times, data checks, errors, and measured recovery point/duration. The reported SQL-marker drill above does not replace application-specific transaction checks.

A production routing switch is a separate operational step after acceptance. Restore intended domains and reapply specs before changing DNS; validate TLS, application data, monitoring, and watchdog down/recovery receipt. Do not point production traffic at an unverified exercise host.

## Target recovery capabilities

Encrypted external backup automation and independent backup-age alerts now have an implementation in the scheduled backup playbook. The selected RPO is 24 hours and RTO four hours for node-01; successful deployment and marker recovery have operator-reported evidence; failure delivery, precise recovery measurement and application-level acceptance remain open. Once identity, durable jobs/revisions, and controlled deletion exist, extend backups and restore checks to those records and pause/resume workers explicitly. The current implementation has no worker or operation history to recover.

See [Deployment](deployment.md), [Runbook](runbook.md), and [ADR-003](../03-decisions/ADR-003-postgresql-provisioning.md).


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
