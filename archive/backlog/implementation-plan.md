# Prioritized implementation plan

Plan date: 2026-09-22. Based on the [backlog](backlog.md) and
[implementation assessment](implementation-status.md).

## Prioritization and scope

The proposed order first protects existing data and establishes working incident
notifications, then introduces accountable developer access, then expands the
deployment workflow. Observability and safe lifecycle management complete that
workflow. Dependencies determine the order within these priorities.

Keep the current single-host, trusted-workload scope. Use the REST API as the first
supported interface; a portal is not a milestone prerequisite. Host high
availability, hostile multi-tenancy, arbitrary persistent volumes, and automatic
database migration rollback are outside this plan.

The numbered items below are in recommended execution order. They are planning
items, not replacement story IDs. Multiple items may contribute to one story; a
story closes only when all its backlog acceptance criteria pass. Milestones are
outcome gates, not calendar estimates, and are intended to be delivered in order.

## Ordered work

| Order | Milestone | Work and expected result | Stories | Dependencies |
| --- | --- | --- | --- | --- |
| 1 | M1 | Build on the recreated PHP/MySQL watchdog and systemd sender: verify hosting, timer/cron operation, and actual outage/recovery email receipt; configure an application canary probe with a compatible HTTP method. Configure Alertmanager delivery and separately verify its pipeline; add independent detection of watchdog cron/hosting failure. Document response ownership. | OPS-007 | Watchdog code and local test tooling exist; public hosting/recipient configuration and live acceptance evidence remain. |
| 2 | M1 | Schedule backups; encrypt and transfer database dumps plus required configuration/secrets off-host; enforce retention/access controls. Extend the watchdog with separate backup-freshness state so host heartbeats cannot mask failed/overdue backups. Define recovery targets, then restore onto a clean test installation. | OPS-006 | 1 for notifications; separate watchdog signal contract; operator-selected backup storage and recovery targets. |
| 3 | M2 | Add individual authentication, project membership, viewer/developer/operator permissions, and revocation. Apply authorization to every existing project endpoint and define a reusable boundary for future log, metric, secret, and lifecycle endpoints. | OPS-004 | M1; choose the identity provider and membership source. |
| 4 | M2 | Record durable audit events for authentication/access failures, privileged operations, and membership changes. Provide restricted filtering/export, retention, secret redaction, and action/outcome attribution. Enforce event recording for later mutation endpoints. | OPS-001, OPS-004 | 3; items 3–4 release together to avoid unaudited access changes. |
| 5 | M2 | Derive configurable security alerts from audit events, link notifications to evidence, group repeated incidents, and verify delivery/failure visibility. | OPS-002 | 1, 4. |
| 6 | M3 | Introduce a versioned project/application/component schema and storage migrations. Support named components, independent images/commands/ports/replicas, internal service names, and component-specific apply results. Preserve or explicitly migrate existing single-component projects. | DEV-001 | 3–4. |
| 7 | M3 | Add validated per-component resource settings and configurable project quotas/defaults. Enforce workload and network policy, explain rejections, preview policy effects, and check requested allocations against usable host capacity. | DEV-008, OPS-005 | 6; account for shared services and system capacity, not just namespace quotas. |
| 8 | M3 | Add ordinary environment configuration and versioned secret references with per-component assignment, authorized CRUD, redacted responses/events, and controlled rollouts on changes. Include newly stored secrets in backup/restore coverage. | DEV-002, DEV-003 | 2–4, 6. |
| 9 | M3 | Add explicit public/private endpoint settings, assigned URL and certificate status reporting, and policy-controlled outbound destination declarations. Update routing and policy when exposure changes. | DEV-009, OPS-005 | 6–7. |
| 10 | M4 | Separate desired configuration from observed state. Add component rollout/health endpoints, ready/desired counts, active image, diagnostic events, and data service availability. Extend Kubernetes read permissions narrowly. | DEV-006, DEV-008, DEV-010 | 6–9. |
| 11 | M4 | Retain configuration revisions and durable operation outcomes. Add retry/reapply and revision restoration with dependency checks, including missing secret versions, and visible rollout results. Document that database contents/migrations are not reverted. | DEV-007 | 8, 10. |
| 12 | M4 | Expose authorized database attachment details and a tracked recovery request that operators can review, execute using the restore procedure, and report back on. Verify data preservation and cross-project denial. | DEV-010 | 2–4, 6, 10. |
| 13 | M5 | Collect Kubernetes application logs with project/component/instance metadata. Provide authorized search/follow and retained-instance access with visible retention. Restrict direct backend access so users cannot bypass project checks. | DEV-004 | 3, 6. |
| 14 | M5 | Add resource inventory, workload/shared-service CPU and memory collection, storage and quota/request comparisons, dashboards, and stale-data handling. Add CPU/memory and scheduling alerts; complete shared-service and application availability coverage. | DEV-005, OPS-003, OPS-007 | 1, 3, 6–7, 10. |
| 15 | M6 | Add application deletion previews and explicit confirmation, retained data by default, narrowly scoped delete permissions, and retryable cleanup with visible outcomes and audit records. | DEV-011 | 4, 6, 10–11. |
| 16 | M6 | Add project retirement with inventory of credentials/data/backups, explicit retention or deletion decisions, access revocation, retryable cleanup, and an audit of retained/deleted resources. | OPS-008 | 2–4, 15. |

## Milestones and exit criteria

### M1 — Recoverable and observable lab

**Items:** 1–2. **Story target:** OPS-006; operational foundation for OPS-007.

See [M1 implementation details](m1-implementation-details.md) for the proposed
design, backup/restore workflow, repository changes, and acceptance evidence.

**Progress:** the external PHP/MySQL watchdog, authenticated heartbeat endpoint,
host readiness sender, systemd units, and local test tooling are implemented.
The sender checks API and Prometheus readiness, then updates a single external
heartbeat; it does not pass through Alertmanager. Optional probing currently uses
HEAD against one fixed HTTPS URL. The watchdog attempts state-change email, but
the repository does not establish public deployment or actual message receipt.
Complete and verify this foundation rather than recreate it. Scheduled encrypted
off-host backups and the restore exercise remain outstanding.

- A backup is created on schedule, stored encrypted off-host, and recovered with
  its required configuration/secrets onto a clean installation.
- The recovery exercise verifies project data, permissions, re-created workloads,
  and ingress and records results against the agreed recovery targets.
- Failed/overdue backup and external availability checks reach the configured
  destination; notification delivery failures can be detected.
- Demonstrate host-heartbeat expiry and recovery, public canary failure,
  Alertmanager delivery failure, and watchdog cron/hosting failure. Keep platform,
  alert-pipeline, and backup signals independent so one cannot refresh another.

This milestone protects current users before introducing new self-service scope.
OPS-007 remains open until the coverage added in M5 is verified.

### M2 — Accountable project access

**Items:** 3–5. **Story targets:** OPS-001, OPS-002, OPS-004.

- At least two test identities in different projects exercise allowed and denied
  operations; viewer and operator permissions are verified separately.
- Revocation blocks subsequent requests. Access and privileged changes produce
  attributable audit records with enforced retention and restricted export.
- Tests demonstrate that responses, audit exports, and notifications omit secret
  values; security notification delivery and grouping are exercised.

All later endpoints must use these authorization and audit boundaries. Recheck
OPS-004 as logs, metrics, secrets, and deletion become available; admin credentials
must not become the developer access mechanism.

### M3 — Configurable multi-component deployment

**Items:** 6–9. **Story targets:** DEV-001, DEV-002, DEV-003, DEV-009, OPS-005;
configuration foundation for DEV-008.

- A web component and private worker deploy together, communicate internally,
  and update independently with distinct commands, configuration, and secrets.
- Existing project specifications survive migration or use a documented,
  validated migration path without data loss.
- Environment/secret changes report activation; secret replacement causes the
  intended rollout and exposes adoption state without revealing values.
- Quota/policy violations produce actionable errors. Admission uses aggregate
  requested allocations and reserved shared-service capacity; changes show impact.
- Public/private transitions remove obsolete exposure. A controlled real-domain
  check verifies TLS status, and outbound allow/deny behavior matches policy.

M3 needs basic configuration adoption reporting; M4 expands this into continuous
health and diagnostics. DEV-008 remains open until scheduling failures are visible.
New secret storage is included in a repeated recovery exercise before release.

### M4 — Diagnosable deployment and recovery

**Items:** 10–12. **Story targets:** DEV-006, DEV-007, DEV-008, DEV-010.

- Healthy, bad-image, unready, and unschedulable deployments show distinct,
  actionable states, ready counts, and active versions.
- A partially failed operation can be retried without duplicate resources or
  database loss; a retained revision can be reapplied and its rollout observed.
- Recovery detects unavailable secret versions and never claims to roll back
  database contents or migrations.
- Developers see their data service's availability and can track a recovery
  request through an operator-run restoration; cross-project access is denied.

Implement durable status and bounded retries first. Introduce a background worker
only if it is needed for reliable observation/recovery; it is not a substitute for
user-visible outcomes or a separate backlog goal.

### M5 — Project diagnostics and capacity visibility

**Items:** 13–14. **Story targets:** DEV-004, DEV-005, OPS-003, OPS-007.

- A developer searches and follows only authorized workload logs, including
  retained logs after an instance is terminated, with visible source and retention.
- Resource views compare measured usage, requests, limits, and quotas and clearly
  distinguish zero usage from missing/stale data.
- Operators see host, shared-service, project, and storage usage, allocation
  pressure, and unschedulable workloads.
- Controlled service failures exercise control-plane, ingress, database,
  monitoring, and application checks, with affected-project context where known.
  External detection still works when the host and local monitoring are down.

Do not expose Loki or Prometheus directly to developers without the project access
boundary, even if the presentation layer already filters by project.

### M6 — Safe application and project retirement

**Items:** 15–16. **Story targets:** DEV-011, OPS-008.

- Application deletion previews match the resources actually removed; default
  deletion preserves persistent data.
- Project retirement revokes access/credentials and records every deleted or
  retained resource, including backup retention decisions.
- Destructive data deletion requires explicit project-specific confirmation;
  changed deletion scope invalidates earlier confirmation.
- Failure injection demonstrates resumable cleanup without touching another
  project, and the final result is visible and auditable.

## Delivery and validation

For each item, update API documentation, operational procedures, and
[implementation status](implementation-status.md) alongside code. Add focused
tests of observable behavior: authorization boundaries, partial failures,
configuration migration, secret handling, and data retention where applicable.
Use the existing smoke/isolation scripts as starting points, extending them for
the milestone's live acceptance scenarios. Perform destructive recovery and
deletion checks in a disposable test installation.

Record evidence for every milestone exit criterion before closing its stories.
Revisit priorities after each milestone using operational incidents and developer
feedback. The sequence intentionally leaves dashboards and deletion after core
data protection, access control, deployment, and recovery capabilities.
