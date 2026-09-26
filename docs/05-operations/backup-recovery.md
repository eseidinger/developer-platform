# Backup and Recovery

Status: current commands reviewed against [backup.sh](../../scripts/backup.sh), Compose, and the API at the source baseline in the [backlog evidence](../04-development/delivery-backlog.md#evidence-conventions). The SQL restore/reapply sequence is carried forward from the archived operations guide and adapted to current paths. **No backup, SQL import, cluster recreation, or application recovery was executed for this documentation update.** Syntax checks do not establish recoverability.

## Current backup scope

| Data | Current mechanism | Remaining responsibility |
| --- | --- | --- |
| Project databases, roles and password hashes | Local compressed `pg_dumpall` | Encrypt, copy off-host, define retention, and prove restore |
| Platform metadata | Same dump includes `platform.projects` with latest specs/status | No revision history, jobs, or audit records exist |
| `.env`, especially `DATABASE_KEY` and `POSTGRES_PASSWORD` | Separate operator-managed copy | Encrypt and retain access independently of the platform host |
| Caddy data/config and customized Grafana state | Compose volumes; not included in SQL dump | Separate backup/recreation procedure and validation |
| Infrastructure, alert rules, workload image identities | Repository revision and external artifact storage | Retain compatible images and record versions/digests |
| External watchdog MySQL/configuration | Separate hosting service | Back up through the hosting provider; PostgreSQL dump excludes it |

The workload contract has no PVCs; durable application data belongs in PostgreSQL. Identity-provider state, job/revision metadata, and retained-resource inventories belong to the target architecture and are not current backup artifacts.

## Set up encrypted off-host storage

Use the [backup repository playbook](../../ansible/README.md#encrypted-s3-backup-repository-setup)
to install restic, configure private S3 credentials and a separately recoverable
repository password, and explicitly initialize a new repository when needed.
This prepares storage only. The separate [scheduled backup playbook](../../ansible/README.md#scheduled-backups-and-independent-backup-alerts)
adds capture, exact-snapshot readback, retention and independent backup alerts;
target-host execution and isolated application restore acceptance remain open. The confirmed policy and
implementation evidence are tracked under OPS-006 in the
[delivery backlog](../04-development/delivery-backlog.md).

## Make a current backup

Run from the repository root on the source host, with PostgreSQL running and access to its Compose project. An Ansible installation requires a privileged shell in `/opt/developer-platform`.

```bash
bash scripts/backup.sh
```

The script creates `.runtime/backups/postgres-<UTC timestamp>.sql.gz` with private permissions. It writes to a temporary file and publishes the final name only after `pg_dumpall` and gzip succeed. It includes role password hashes and all databases. Select the exact path printed by the script; do not select an unfinished `.tmp` file.

```bash
backup_file=.runtime/backups/postgres-REPLACE_WITH_TIMESTAMP.sql.gz
gzip -t "$backup_file"
sha256sum "$backup_file"
```

Replace the placeholder before execution. Record the checksum, source revision, PostgreSQL version, UTC time, and backup identifier alongside the encrypted recovery bundle. Gzip integrity is not SQL or data validation. Coordinate application writes if the recovery scenario needs consistency across multiple databases; this dump does not provide a single cross-database application transaction snapshot.

Encrypt the dump and `.env` using the operator's selected backup system, copy them off-host, and verify retrieval and decryption. The scheduled backup playbook supplies encryption/upload/scheduler/retention automation; this manual SQL command alone does not invoke it. Confirm the installation-specific recovery targets, storage, recipients and retention before operational acceptance. Preserve the original `DATABASE_KEY`: generating a replacement will produce credentials that do not match restored roles.

## Restore into an isolated installation

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
backup_file=/absolute/private/path/postgres-REPLACE_WITH_TIMESTAMP.sql.gz
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

The API has no background reconciler. Bootstrap recreates cluster/controller credentials, but does not restore application workloads until PUT is repeated.

## Reapply restored projects

Use this after SQL restore, or after cluster recreation with intact PostgreSQL volumes. The following commands target only the local API. They apply every stored project's latest spec, so review the catalog before running the Python block and ensure this is the intended recovery installation.

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

For each project, use the [runbook](runbook.md#application-unhealthy-after-deployment) to inspect rollout and routing, then execute the application's own data checks. For `hello`, for example:

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello rollout status deployment/hello --timeout=180s
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

The echo example does not exercise PostgreSQL. Use a database-backed application with known pre-backup records: verify those records survived, then write and read a new record through the application. Verify database ownership, login permissions, and denied foreign-project access. Preserve private import logs and record source/target environments, code/image versions, backup ID/checksum, start/end times, data checks, errors, and measured recovery point/duration. No such completed exercise is recorded by this documentation update.

A production routing switch is a separate operational step after acceptance. Restore intended domains and reapply specs before changing DNS; validate TLS, application data, monitoring, and watchdog down/recovery receipt. Do not point production traffic at an unverified exercise host.

## Target recovery capabilities

Encrypted external backup automation and independent backup-age alerts now have an implementation in the scheduled backup playbook. The selected RPO is 24 hours and RTO four hours for node-01; live deployment, failure delivery, measured recovery and a full application acceptance harness remain open. Once identity, durable jobs/revisions, and controlled deletion exist, extend backups and restore checks to those records and pause/resume workers explicitly. The current implementation has no worker or operation history to recover.

See [Deployment](deployment.md), [Runbook](runbook.md), and [ADR-003](../03-decisions/ADR-003-postgresql-provisioning.md).


## Retrieve a scheduled recovery bundle

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
