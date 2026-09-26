# Operations Runbook

Status: current administrator procedures reviewed against source; commands were not run against a live installation for this update. See the [backlog evidence](../04-development/delivery-backlog.md#evidence-conventions) for checks actually performed. Run commands from the repository root on the affected host; an Ansible installation requires a privileged shell in `/opt/developer-platform`.

## Inspect the current installation

```bash
docker compose ps
curl --fail-with-body http://127.0.0.1:8000/healthz
curl --fail-with-body http://127.0.0.1:8000/readyz
curl --fail-with-body http://127.0.0.1:9090/-/ready
docker compose exec -T postgres pg_isready -U postgres -d platform
kubectl --kubeconfig .runtime/admin.kubeconfig get nodes -o wide
kubectl --kubeconfig .runtime/admin.kubeconfig get pods -A
```

`/healthz` is process health; `/readyz` checks PostgreSQL and Kubernetes connectivity. PostgreSQL readiness is not a data-integrity or application-permission check. Record time, host, code revision (`git rev-parse HEAD`), affected project, latest spec, and observed symptoms. The current API has no operation IDs, revision history, durable job steps, or per-user audit trail. Preserve available logs and redact credentials before sharing them.

## Provisioning stuck or failed

In a trusted shell with tracing disabled, load the admin credentials and list stored projects:

```bash
eval "$(python3 scripts/env.py)"
curl --fail-with-body http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer $PLATFORM_TOKEN"
docker compose logs --tail=100 platform-api postgres
```

`provisioning` can remain after process termination. `failed` records a provisioning error; `applied` means resource application completed, not that the workload is healthy. Early dependency failures can prevent any status update. Check the dependency commands above and inspect existing Kubernetes resources before retrying after an ambiguous timeout.

For the example project `hello` (substitute the actual project and namespace):

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get pods,svc,ingress
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello describe pods
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get events --sort-by=.metadata.creationTimestamp
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello logs deployment/hello --tail=100
```

After fixing permissions, image, quota, or dependency failures, repeat PUT with the project's complete intended spec. For the unchanged sample:

```bash
curl --fail-with-body -X PUT http://127.0.0.1:8000/projects/hello \
  -H "Authorization: Bearer $PLATFORM_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @examples/project.json
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello rollout status deployment/hello --timeout=180s
```

Use the actual saved spec for an existing application; the sample would replace its image and port. [Recovery](backup-recovery.md#reapply-restored-projects) shows how to retrieve and reapply the stored catalog. There is no background worker to resume. PUT preserves existing databases, provided the configuration and database credentials remain compatible. Do not delete a database to repair a failed workload.

## Application unhealthy after deployment

Inspect rollout, logs, pod events, image pulls, resource limits, probes, and database connectivity. Compare the desired image/port with your externally retained prior spec and migration records; the platform stores only the latest spec. A manual rollback is another PUT of a known compatible spec, followed by rollout and application verification. It does not roll back database schema changes.

For the default local sample route:

```bash
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

Use the configured HTTPS hostname for public applications. The sample only echoes HTTP; acceptance additionally requires an application-specific PostgreSQL write/read with known test data.

## External heartbeat missing

Check the sender on the platform host:

```bash
sudo systemctl status platform-heartbeat.timer
sudo systemctl status platform-heartbeat.service
sudo journalctl -u platform-heartbeat.service -n 50 --no-pager
```

The oneshot service can be inactive between successful runs; inspect its last result and timer schedule. It sends only when API dependency readiness and Prometheus readiness pass. Check those endpoints first, then sender connectivity, endpoint/token configuration, and TLS without printing secrets.

On the external watchdog host, inspect the hosting scheduler or `crontab -l`, PHP CLI extensions, and cron diagnostics using the [watchdog guide](../../operations/watchdog/README.md). A stale cron makes the status page unavailable, but has no independent notifier. Manually running cron can send real email; use the documented alert exercise with intended recipients. Verify both the down and recovery notifications. A heartbeat alone does not verify application data or Alertmanager delivery.

## Docker or k3d unavailable

Inspect host disk/memory, Docker logs, and node status before changing resources. PostgreSQL and monitoring are outside k3d and should survive a cluster-only outage. Use the [start/stop procedure](deployment.md#current-installation-and-lifecycle) after resolving the cause; do not begin by deleting volumes or the cluster. If the cluster must be recreated, retain database volumes and [reapply stored specs](backup-recovery.md#reapply-restored-projects). No reconciler automatically restores workloads.

## PostgreSQL unreachable or slow

Use the readiness and service-log commands above. Inspect host disk, connection limits, locks, database permissions, and connectivity from the affected workload. A read-only connection/activity summary is:

```bash
docker compose exec -T postgres psql -X -U postgres -d platform -c \
  'SELECT datname, usename, state, wait_event_type, count(*) FROM pg_stat_activity GROUP BY datname, usename, state, wait_event_type;'
```

Resolve the cause without granting blanket superuser access. Verify application connectivity and write/read behavior afterwards.

## Low disk space or failed backup

```bash
df -h
df -i
docker system df
docker compose logs --tail=100 postgres
```

Attribute growth before removing anything. Never remove unidentified volumes. Follow [backup creation and verification](backup-recovery.md#make-a-current-backup); the manual SQL script alone has no off-host upload or freshness alert. If the scheduled backup playbook is deployed, inspect its independent status and notification channel below. A completed dump does not prove recoverability.

## Compromised credential or access revocation

The API uses one shared administrator token; individual user revocation and scoped audit are not implemented. Coordinate replacement of `PLATFORM_TOKEN` in `.env` and recreate the API container so it receives the new environment. Revoke access to the old credential at its distribution points.

Preserve `DATABASE_KEY` during recovery. Changing it changes derived Secrets but does not update existing PostgreSQL role passwords; rotation requires coordinated role-password and workload-Secret changes. Follow the [platform configuration notes](../../platform/README.md#configuration). The root [operations notes](../../README.md#operations) describe controller-token rotation. Never include secret values in incident records.

## Closure and target capabilities

Record affected resources, commands, results, actual recovery duration, and remaining uncertainty. Verify an application request, database write/read, and relevant recovery notifications.

Revision-bound rollback, resumable operation IDs, retained-resource deletion inventories, and per-user audit investigation remain target procedures in the [software architecture](../02-architecture/software-architecture.md). They cannot be used as current incident prerequisites.


## Scheduled backup failed or interrupted

If the optional backup automation is deployed, inspect:

```bash
sudo systemctl status platform-backup.service platform-backup.timer --no-pager
sudo journalctl -u platform-backup.service -n 40 --no-pager
sudo cat /var/lib/developer-platform-backup/status.json
sudo systemctl status platform-backup-notify.timer --no-pager
sudo journalctl -u platform-backup-notify.service -n 20 --no-pager
```

A failure after readback can retain a valid `last_verified_snapshot`; notification
failure is recorded separately in `notification.json`. Restore S3/watchdog access,
then use `sudo systemctl start platform-backup-notify.service` to retry delivery.
For a failed capture/upload, resolve the reported stage and restart the backup
service. The host heartbeat cannot clear backup failures.

If `/var/lib/developer-platform-backup/resume.json` remains, exact container IDs
still require restart. Inspect them before replacing/removing containers. The
recovery service retries all recorded services even if one fails:

```bash
sudo systemctl start platform-backup-recover.service
```

Do not run recovery concurrently with capture or remove the process lock. Avoid
`restic unlock` until all restic processes have stopped and a stale repository lock
has been established. Unverified/pending snapshots require investigation; do not
count them as recovery points. See the [backup deployment guide](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts)
for service interruption, retention and restore limits.
