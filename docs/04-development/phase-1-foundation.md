# Phase 1 – Foundation and Usable Vertical Slice

Status: partially implemented; acceptance gate remains open. The inspected Python API, PostgreSQL/Kubernetes provisioning, hybrid infrastructure, monitoring, and watchdog tooling provide the foundation. The [implementation alignment report](implementation-alignment-report.md) records passing local checks and remaining source gaps; live application/database acceptance, failure recovery, isolated restore, and alert receipt remain unverified. Covers [F-01 through F-06, F-08, and N-01 through N-08](../01-product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](delivery-backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Create, update, observe, and deliberately remove a web application with PostgreSQL on the existing hybrid host using a minimal API/CLI.

## Ordered work packages and acceptance gates

The [delivery backlog](delivery-backlog.md) supplies binding acceptance criteria and the [development plan](development-plan.md#backlog-delivery-commitments) maps every story. These gates are open. Deliver in order; use disposable resources for failure and recovery checks.

### 1A — Operational protection

Inventory the current installation and reproduce the hybrid profile. Complete and verify the existing watchdog and notification infrastructure before expanding self-service.

- Configure real Alertmanager and external watchdog destinations, recipients, escalation ownership, grouping and recovery messages. Record actual receipt and delivery-failure visibility, not just successful mail handoff.
- Independently exercise host heartbeat expiry/recovery, k3d failure, a public application canary with compatible method and expected content, Alertmanager delivery failure, and external watchdog cron/hosting failure. A separate observer must notify when the watchdog itself fails. Keep platform, alert-pipeline and backup signals separately authenticated and timestamped so one cannot refresh another.
- Schedule encrypted off-host backups of databases/roles, platform state, configuration and recovery secrets, plus required service state. Record the selected storage, schedule, retention/access policy, independently recoverable keys, RPO/RTO, and replacement-host path before acceptance.
- Verify exact backup retrieval/integrity and recovery credentials; failed uploads must not advance successful capture time. Test failed/overdue/stalled backups and missing signals, including when local monitoring is down. Bound job duration and prevent overlapping capture/retention operations.
- Restore into an empty isolated installation without relying on the original host. Verify application data write/read, permissions, recreated workloads, ingress, monitoring and alerts. Record measured data loss and recovery time against selected targets. Test corrupt/unavailable backups and unavailable keys; do not treat extraction or SQL process exit as proof of recovery.

Repeat recovery acceptance after changes to stored secrets/state, backup format, database major version or bootstrap behavior; schedule recurring exercises. Local fixtures do not establish off-host recovery or actual alert receipt. OPS-006 closes only with all its evidence; OPS-007 remains open for Phase 2 coverage.

### 1B — Accountable access and security events

Release scoped individual authentication and durable audit together. Choose the identity/membership source and explicitly resolve applicable IAM decisions without requiring the richer Phase 3 experience.

- Enforce viewer/developer/administrative permissions for every project/environment operation, including logs, metrics, secrets and jobs. A developer never uses the shared administrator token. Revoke a platform grant and prove the next request is denied and audited.
- Record actor, scope, timestamp, action, target, revision/operation where applicable, and result. Include authentication/access failures, privileged operations and membership changes. Redact secrets; define retention and tamper protection, restrict access, and prove developers cannot alter audit records.
- Inspect project permissions, workload security settings and network policies. Filter/export audit records over a selected time window without secret disclosure.
- Configure security-event rules for authentication failures, denials and privileged changes. Notifications include severity, time, affected resources and supporting event references. Test destinations, delivery failures and repeated-event grouping without hiding an ongoing incident.

OPS-001, OPS-002 and OPS-004 require all backlog criteria to pass. Reapply these boundaries to every later endpoint.

### 1C — Durable single-application lifecycle

Implement the project/environment/application identity and supported single-image profile with stable IDs and minimally separated provider ports. Persist desired revisions and asynchronous jobs atomically before side effects; return an operation ID, expose authorized progress, and resume after worker interruption. Phase 2 hardens this baseline and adds revision selection, concurrency guarantees and portability.

- Validate the supported single-image profile and reject unknown fields or unsupported capabilities before side effects; preserve technology-independent public identities and provider boundaries.
- Deploy a sample application in a fresh environment and write/read PostgreSQL through it. Bind managed configuration/secrets, deny foreign-project database access, preserve data across updates and repeat identical requests without duplicate resources.
- Exercise an authorized application restart without changing its desired spec or deleting data; record the operation and observe recovery readiness.
- Interrupt provisioning after database creation and fail a deployment; retry resumes safely with durable, visible outcomes. Distinguish accepted configuration from observed readiness. Show desired/ready counts, active image and reasons for bad-image, unready, stalled and unschedulable states.
- Provide validated ordinary configuration CRUD and separate authorized secret CRUD with redacted views/events. Report rollout requirements and activation/adoption; rotate credentials through successful reconnection and include new secret state in backup/restore acceptance.
- Provide basic authorized logs, metrics and resource inspection for diagnosis. Mark missing/stale telemetry explicitly. Measure host/shared-service/workload/storage consumption and reserve before setting capacity targets.
- Preview application deletion with affected workload, routes and configuration; require explicit confirmation, invalidate it if scope changes, retain persistent data by default, and expose completion/partial failure. Persist retained-resource inventory and audit; retry cleanup safely. Data deletion requires separate explicit authorization.
- Document and exercise the minimal API/CLI flow, deployment versions, installation parameters, operational commands and failure responses.

Single-image acceptance is only a slice of stories with per-component criteria. Phase 2 completes detailed diagnostics, policy/scaling/connectivity and recovery workflows before the richer interfaces in Phase 3.

## Outside this phase

A complete portal, broad data-service catalog, HA PostgreSQL, multi-cluster support, AI, and an implementation-language rewrite. Quarkus may serve as a sample application without rebuilding the control plane.

Dependencies: [Deployment](../05-operations/deployment.md), [Monitoring](../05-operations/monitoring.md), [Backup and recovery](../05-operations/backup-recovery.md).
