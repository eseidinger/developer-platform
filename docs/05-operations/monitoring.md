# Monitoring and Alerting

Status: operational draft based on [ADR-005](../03-decisions/ADR-005-observability-watchdog.md).

## Current inspection and evidence

The [runbook](runbook.md#inspect-the-current-installation) contains dependency and workload checks; [heartbeat diagnostics](runbook.md#external-heartbeat-missing) covers the systemd sender and external scheduler. Installation commands live in the [watchdog guide](../../operations/watchdog/README.md) and [deployment playbooks guide](../../operations/watchdog/ansible/README.md).

Prometheus currently scrapes itself, node-exporter, and kube-state-metrics; Alloy collects host Docker logs. Alertmanager defaults to a `local-only` receiver. The [SMTP deployment playbook](../../operations/alertmanager/README.md) configures authenticated email from an inventory with a private password prompt; actual delivery still requires acceptance. The external watchdog can send state-change mail through PHP mail or authenticated TLS SMTP. Its host sender checks API dependency readiness and Prometheus readiness. Project telemetry endpoints, maintenance windows, and a separate local notification service are not implemented. Independent backup-age/failure checks now exist in the optional backup watchdog channel; source backup deployment has operator-reported evidence; actual backup-specific alert receipt still requires verification.

The [backlog evidence](../04-development/delivery-backlog.md#evidence-conventions) records passing local watchdog freshness and SMTP fixture tests. The operator confirmed heartbeat outage/recovery mail and recovery after correcting the HTTPS probe from HEAD to GET. Recovered Prometheus/Grafana health and all three scrape targets also passed. Broader cluster/host failure exercises, Alertmanager delivery, and backup-specific mail remain subject to the current backlog; see [current monitoring progress](../04-development/delivery-backlog.md#current-monitoring-progress). Commands in the runbook were reviewed against source, not executed as live acceptance for this update.

## Target coverage and alert contract

The remaining sections describe intended operational coverage, including capabilities that still need implementation.

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

Each alert has severity, affected resource, start time, last observation, runbook reference, and an assigned recipient. Record impact and changes during incidents; group recurring related alerts.

**Accepted lab response policy (September 27, 2026):** The project owner is the sole responder for alerts delivered to the existing alert email inbox. The target is to acknowledge and begin investigation within 24 hours of notification, reflecting operation as a side project alongside regular work. This is a response target, not a resolution deadline. There is no secondary responder or escalation coverage. Automated detection and notifications continue independently of operator availability.

Under [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md), the existing external watchdog is the end of the lab monitoring chain. No additional external service is required to monitor its hosting or scheduler. Silent watchdog failure, including missed platform or backup notifications during that failure, is an accepted limitation rather than outstanding acceptance work. Manual status/scheduler inspection remains available; it does not provide independent notification.

## Operational checks

On introduction and after alert-channel changes, trigger a test failure, confirm receipt, and verify recovery. After monitoring upgrades, check scrapes, project filters, dashboards, and the external watchdog.

Daily or automated review covers critical alerts, overdue jobs, backup success, and resource growth. Restore exercises follow the agreed backup policy.

The [Runbook](runbook.md) describes responses; [Observability architecture](../02-architecture/observability.md) covers data flows and permissions.


## Scheduled backup monitoring

Deploy the separate `backup.php` channel and [scheduled backup job](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts)
for capture-time freshness independent of host heartbeat. The backup channel alerts
on explicit failure, no success, age over 24 hours or an attempt running over two
hours. Local `status.json` distinguishes verified storage from pending notification;
`platform-backup-notify.timer` retries undelivered events every five minutes.
Neither host heartbeats nor authenticated GET preflight refresh backup age.

Verify a real BACKUP DOWN/UP cycle after deployment. Use controlled, reversible exercises on the existing lab platform and watchdog,
following [ADR-010](../03-decisions/ADR-010-single-environment-lab.md). A separate
test installation is not required. Describe impact, retain original settings,
restore normal operation and verify recovery; do not forge a success signal for
a backup that has not passed readback. No timer or external channel
establishes isolated SQL/application restoration by itself.
