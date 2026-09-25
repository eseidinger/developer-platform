# Operations Runbook

Status: initial target procedures, to be validated against a real installation. Add actual hostnames, access details, and commands from the implementation repository. These procedures do not imply completed execution.

## General incident procedure

Record impact, time, project/environment, revision, and operation ID. Distinguish host, network, runtime, database, and application failure domains first. Preserve telemetry and recent changes; redact secrets.

Limit interventions to the affected scope. Establish backup/recovery status before modifying data. After an intervention, verify health and an application-level write/read operation, then close the incident with a traceable record.

## External heartbeat missing

1. Check the last receipt, external scheduler, and notification channel.
2. Check host reachability through an independent administrative path.
3. If the host is reachable, inspect the sender, token, TLS, time, and outbound network path.
4. If the host is lost, evaluate provider/network status and recovery using [Backup and recovery](backup-recovery.md).
5. Confirm heartbeat recovery and service health separately.

A working heartbeat does not rule out database or application failure.

## Docker or k3d unavailable

Check host disk, memory, and daemon/system logs. During a k3d-only failure, external PostgreSQL and monitoring services should remain available. Do not start by deleting volumes or the entire cluster.

After recovery, verify nodes, ingress, database connectivity, and applications. The reconciler observes existing resources before resuming jobs.

## Provisioning stuck or failed

Inspect the operation, current revision, last successful step, and provider result. After an ambiguous timeout, identify provider resources first. Check permissions, quotas, registry access, and networking.

Resume the same operation after fixing the cause. Do not delete an existing database as a cleanup shortcut. Remove orphaned resources only after establishing ownership and inventory.

## Application unhealthy after deployment

Compare old and new image/configuration revisions and database migrations. Check readiness, logs, resources, and dependencies. Roll back to a known revision if the schema is compatible; otherwise use a forward fix or verified recovery plan.

After the intervention, execute an application request and database operation, rather than checking process state alone.

## PostgreSQL unreachable or slow

Check host/container status, disk, database connections, locks, DNS, and connectivity from the workload. Distinguish authentication, permission, and transport failures.

Do not grant blanket superuser access. Identify schema changes and long-running queries before intervention. Afterwards, verify the connection pool and error/latency baseline.

## Low disk space / failed backup

Attribute growth to database data, logs, metrics, images, or volumes. Apply retention and remove known expendable data deliberately; never remove unidentified volumes. Reduce write pressure if database storage is at risk.

Check backup target, access, and capacity; repeat the backup and plan restore verification. A green job without data verification does not resolve a failed backup.

## Compromised credential / access revocation

Identify the affected principal and scope, block access, issue new credentials, and update workloads deliberately. Revoke old credentials and terminate existing sessions according to policy. Review audit records for unauthorized activity; never include secret values in incident reports.

## Closure

Verify recovery alerts, document data loss or unknown impact, and distinguish causes from hypotheses. Address recurrence through tests, monitoring, or an ADR change. Record timestamps and actual recovery duration in operational evidence.
