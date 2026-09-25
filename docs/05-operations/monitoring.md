# Monitoring and Alerting

Status: operational draft based on [ADR-005](../03-decisions/ADR-005-observability-watchdog.md).

## Minimum coverage

| Area | Checks | Response |
|---|---|---|
| Host | Reachability, disk/inodes, RAM, I/O, time | Investigate host/storage failure |
| Docker / k3d | Daemon, nodes, restarts, unready workloads | Identify failure domain |
| Platform API / worker | Health, errors, job age, repeated retries | Provisioning incident |
| PostgreSQL | Reachability, connections, locks, free space | Database incident |
| Edge | External route, certificate expiry, TLS | Routing/certificate checks |
| Backup | Age, success, external target, restore evidence | Prioritize backup failure |
| Monitoring itself | Scrape success, storage, alert delivery | Watchdog/monitoring incident |

Thresholds depend on measured baselines and operational goals. For example, disk space below 20% could trigger a warning and below 10% a critical alert; these are proposed starting values, not accepted rules. Also consider trends and absolute free capacity.

## Watchdog contract

Proposed starting values: heartbeat every minute, overdue after five minutes, external check every minute. Nominal detection is therefore about five to six minutes after the last heartbeat; verify the web host's actual scheduler frequency. A cron job running only every five minutes increases detection time accordingly.

The receiver authenticates the sender, uses server-side receipt time, and stores the target ID and last state. Repeated requests must be safe. Implement token rotation and rate limits; tokens must not appear in URLs or logs.

Deduplication sends an alert on state change and a recovery notification when service returns. Maintenance windows have an expiry. The heartbeat complements external health probes; it does not alone prove healthy PostgreSQL or application services.

## Alert process

Each alert has severity, affected resource, start time, last observation, runbook reference, and an assigned recipient. Actual contacts remain open. Record impact and changes during incidents; group recurring related alerts.

## Operational checks

On introduction and after alert-channel changes, trigger a test failure, confirm receipt, and verify recovery. After monitoring upgrades, check scrapes, project filters, dashboards, and the external watchdog.

Daily or automated review covers critical alerts, overdue jobs, backup success, and resource growth. Restore exercises follow the agreed backup policy.

The [Runbook](runbook.md) describes responses; [Observability architecture](../02-architecture/observability.md) covers data flows and permissions.
