# ADR-015 – Encrypted Recovery Bundles with Verified-Only Retention

Recorded: September 27, 2026. Status: **Implemented design; owner acceptance of this record not recorded**. The owner-selected storage/schedule/RPO/RTO policy and partial operational evidence are recorded under [OPS-006](../04-development/delivery-backlog.md#current-backup-and-recovery-progress).

## Context

Recovering a recreated cluster requires SQL roles/data, platform configuration and credential continuity, plus selected service state. A successful upload alone does not prove that the captured bundle is retrievable; host heartbeats do not prove backup freshness.

## Implemented choice

A root-run systemd job uses a process lock and a two-hour timeout. It captures compressed `pg_dumpall`, deployed sources and `.env`, host configuration/helpers/units, stopped Caddy/Grafana volume archives and version/image metadata. Restart intent records exact container IDs before stopping; finalization, ExecStopPost and boot recovery retry those restarts. PostgreSQL remains online; the dump is not one transaction across databases.

Restic encrypts the bundle to S3. Upload creates a `pending` snapshot; the job restores that exact snapshot and compares the manifest and every listed checksum. Only after readback does it retag `verified` and record the resulting full snapshot ID and original capture-start time. Retention selects only this installation's `developer-platform,verified` snapshots, keeps the latest plus 14 daily/8 weekly/6 monthly points, prunes and runs repository checks. Pending snapshots are retained for investigation; overlapping retention rules do not promise 28 distinct snapshots.

The timer runs at 00:00 and 12:00 UTC. Selected targets are RPO 24 hours and RTO four hours, not measured guarantees. A separate authenticated watchdog backup channel stores start/success/failure and capture-time freshness independently of host heartbeat. A durable local outbox retries transport every five minutes. Local verified snapshot state and notification state remain distinguishable: later retention/notification failures can coexist with a valid recovery point.

## Alternatives and consequences

SQL-only backups omit configuration/credential/service recovery. Raw volume capture would require database-consistency design. WAL/PITR or live snapshot strategies could reduce data loss or avoid service pauses, but are not implemented. Upload-success-only retention could count unreadable snapshots as recovery points.

Caddy/Grafana capture briefly interrupts routing and dashboards. Plaintext staging/readback needs protected disk space for two copies. Images are recorded rather than exported; compatible artifacts must remain available. Kubernetes node files, generated cluster credentials, historical Prometheus/Loki/Alertmanager volumes and external watchdog state are excluded. Discovery is rebuilt from the catalog. External watchdog backups and independently recoverable restic/S3 credentials remain separate responsibilities.

Checksum readback proves bytes, not SQL import, application transactions or RPO/RTO. The backup and heartbeat channels still share watchdog hosting/mail; silent watchdog failure remains accepted under ADR-011.

## Evidence and evolution

Source: [runner](../../operations/backup/scripts/backup-platform.py), [systemd/deployment configuration](../../operations/backup/ansible/deploy-backup.yml), [watchdog transitions](../../operations/watchdog/src/backup.php). [Backup procedures](../../operations/backup/README.md) document deployment, retention and controlled in-place drills. Operator-reported scheduled capture, marker restore and selected email receipt do not close all OPS-006/007 criteria.

New isolated restore environments remain deferred under ADR-010. Revisit backup format/scope when identities, secrets, revisions, jobs or persistent workload volumes are added, or when important data requires finer RPO, PITR or fewer service interruptions.
