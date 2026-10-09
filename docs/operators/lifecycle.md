# Platform lifecycle

Status: current procedures with planned upgrade requirements called out
explicitly. Last reviewed October 9, 2026.

Installation is covered separately for [local](install-local.md) and
[remote](install-remote.md) environments.

## Stop and restart

Stop the shared services and workload cluster without deleting data:

```bash
docker compose stop
.runtime/bin/k3d cluster stop workloads
```

Start the existing installation or rebuild the API from current sources:

```bash
bash scripts/up.sh
```

Bootstrap starts an existing k3d cluster; it does not migrate the Kubernetes
image or reapply saved application declarations automatically. Expected heartbeat
alerts may fire during dependency downtime because maintenance windows are not
implemented.

The Ansible deployment validates configuration, prevents overlap with protected
drills, and recreates shared-service containers without deleting volumes. This is
a shared-service outage, not a rolling control-plane deployment.

## Recreate the workload cluster

This removes Kubernetes workloads and cluster resources. First create and verify
a [backup](backup-and-recovery.md), preserve `.env`, record versions, and retain
any manually managed manifests.

```bash
bash scripts/down.sh
# Change K3S_IMAGE in .env here only as part of a planned migration.
bash scripts/up.sh
```

Without `--volumes`, the command preserves Compose service volumes, including
PostgreSQL and the platform catalog. Reapply the stored declarations and verify
application data. Retaining a PostgreSQL volume is not a supported major-version
upgrade by itself.

`bash scripts/down.sh --volumes` deletes the cluster and persistent Compose data.
It is only for a deliberate disposable-lab reset. Both modes retain `.env`, local
backup files, and installed tools.

## Rotate the controller credential

The external controller uses a restricted, long-lived Kubernetes ServiceAccount
token. Delete only the `provisioner-token` Secret, rerun `scripts/up.sh`, and
restart `platform-api`. Verify `/readyz` and a representative deployment
operation. Do not rotate it by deleting unrelated cluster credentials.

## Platform upgrade

There is not yet a generally accepted zero-downtime platform-upgrade procedure.
For an upgrade on the lab:

1. Define the exact source and image versions and affected state schemas.
2. Create a verified backup and record the rollback conditions.
3. Pause incompatible jobs or drills.
4. Deploy through the normal Ansible or local bootstrap path.
5. Verify API health, readiness, authorization, provider access, monitoring, and
   one representative application workflow.
6. Record migrations, executor, timestamps, results, and unresolved uncertainty.

Application release and rollback are developer workflows. A workload rollback
does not reverse its database schema or restore historical secret values; use
compatible expand/contract migrations.
