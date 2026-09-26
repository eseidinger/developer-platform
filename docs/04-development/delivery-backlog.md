# Delivery Backlog and Acceptance Criteria

Status: open delivery requirements, migrated from the former archive on September 26, 2026. No story is certified complete by this migration. The [development plan](development-plan.md) assigns delivery gates; the [implementation alignment report](implementation-alignment-report.md) records the inspected baseline.

## Conventions and scope

- **Developer:** a user who deploys and manages applications within authorized projects.
- **Operator:** a user who administers the platform, its capacity, and its security.
- **Project:** the boundary for application resources, configuration, and access.
- **Application:** one or more cooperating components, such as a web service and a worker,
  each of which can have its own deployment.
- Story IDs are permanent references. `DEV` identifies developer stories and `OPS`
  identifies operator stories. New stories receive the next unused number in their
  category; reordering or removing stories must not renumber existing IDs.
- Acceptance criteria describe observable outcomes. They do not prescribe a portal,
  CLI, or API implementation.

The platform currently targets trusted workloads on a single host. These stories
do not imply high availability or isolation suitable for hostile tenants.

## Task tracking

Each task belongs to exactly one phase or sub-gate; story IDs remain the overall acceptance gates. `DEV/OPS-xxx-Tnn` tasks inherit the story owner role in the [plan](development-plan.md#backlog-delivery-commitments). `PLAN-nnn` tasks cover existing phase scope outside the original stories and take their owner from the phase work package. Assign named owners before work starts. IDs are permanent; moving a task changes its phase field, not its ID.

Every checkbox is open because implementation/acceptance evidence has not been attached here; it does not mean no source foundation exists. Close a task only after its listed outcome is verified and record date, revision, environment, results and limitations beside it. Close a story only when every original acceptance criterion passes. A Phase 3 design decision does not close deferred implementation tasks.

Phase gates remain **1A → 1B → 1C → 2 → 3 → 4.1–4.5**. Dependencies below supplement these gates and identify ordering within a phase; they do not authorize skipping earlier gates. Deferred tasks have no scheduled phase and cannot block the single-image gates. Component attribution in initial diagnostics uses the single supported component; rerun those checks when the model expands.

Phase 1A runs within the existing administrator-operated boundary; secrets and operational credentials remain protected. Phase 1B establishes individual authorization/audit before expanded self-service. From Phase 1B onward, every task introducing an endpoint, data surface or persisted state must include scoped authorization/revocation, secret redaction and audit checks and update backup coverage. Repeat isolated restore when recovery scope changes. These are part of that task's completion, not an unbounded extra phase. Release OPS-004-T01 with OPS-001-T01; later endpoints reuse the same boundary.

## Phase task index

This index lists execution tasks, not story completion promises. Task details and checkboxes below are authoritative.

| Gate | Tasks |
|---|---|
| 1A | OPS-006-T01, OPS-006-T02, OPS-006-T03, OPS-007-T01 |
| 1B | OPS-001-T01, OPS-001-T02, OPS-002-T01, OPS-004-T01 |
| 1C | DEV-002-T01, DEV-003-T01, DEV-003-T02, DEV-004-T01, DEV-005-T01, DEV-006-T01, DEV-007-T01, DEV-010-T01, DEV-011-T01, OPS-003-T01, PLAN-001 |
| 2 | DEV-004-T02, DEV-005-T02, DEV-007-T02, DEV-008-T01, DEV-009-T01, DEV-010-T02, OPS-003-T02, OPS-005-T01, OPS-005-T02, OPS-007-T02, OPS-008-T01, OPS-008-T02, PLAN-002, PLAN-003, PLAN-004, PLAN-005 |
| 3 | DEV-001-T01, PLAN-006, PLAN-007, PLAN-008, PLAN-009 |
| 4.1 | PLAN-010 |
| 4.2 | PLAN-011 |
| 4.3 | PLAN-012 |
| 4.4 | PLAN-013 |
| 4.5 | PLAN-014 |
| 4 (after 4.5) | PLAN-015 |
| Deferred | DEV-001-T02, DEV-002-T02, DEV-003-T03, DEV-006-T02, DEV-008-T02, DEV-009-T02, DEV-011-T02 |

## Developer stories

### DEV-001 — Deploy applications with multiple components

As a developer, I want to deploy an application composed of multiple components,
so that I can run its services and workers together within one project.

Acceptance criteria:

- Each component can specify its own image, startup command, ports, and replica count.
- Components can communicate through stable internal service names within the project.
- Deployment results identify successful and failed components and explain failures.
- Updating one component does not require redeploying unchanged components.

Phase tasks:

- [ ] **DEV-001-T01 · 3** — Review a concrete multi-component use case and capacity; record contract/migration design, independent-update semantics, and an owner-approved scheduling decision or continued deferral with a review trigger. Prerequisites: Phase 2 gate.
- [ ] **DEV-001-T02 · Deferred** — Implement named components with separate images, commands, ports and replicas; prove stable internal discovery, component-specific success/failure and independent updates, and migrate existing specs without data loss. Prerequisites: DEV-001-T01; explicit scheduling decision.


### DEV-002 — Configure application environments

As a developer, I want to manage non-secret environment variables for each component,
so that I can change application behavior without rebuilding its image.

Acceptance criteria:

- I can view, add, update, and remove variables for an authorized component.
- Invalid configuration is rejected with an actionable error before it is applied.
- Changes indicate whether a rollout is needed and when the new configuration is active.

Phase tasks:

- [ ] **DEV-002-T01 · 1C** — Implement authorized configuration view/add/update/remove with validation before apply; report rollout requirements and observed activation for the single component. Prerequisites: OPS-004-T01; OPS-001-T01; PLAN-001.
- [ ] **DEV-002-T02 · Deferred** — Extend CRUD and activation reporting to independently addressed components; changing one component leaves others unchanged. Prerequisites: DEV-001-T02; DEV-002-T01.


### DEV-003 — Manage application secrets

As a developer, I want to manage secret environment variables separately from ordinary
configuration, so that applications can use credentials without exposing them.

Acceptance criteria:

- I can create, replace, and remove secrets and assign them to specific components.
- Stored values are not returned in ordinary configuration views, logs, or audit records.
- Unauthorized users cannot read or modify secrets.
- I can roll out a replacement secret and see which components have adopted it.

Phase tasks:

- [ ] **DEV-003-T01 · 1C** — Implement separate secret create/replace/remove and authorized binding; prove values stay out of configuration views, logs and audit, and deny foreign-project read/write. Prerequisites: OPS-004-T01; OPS-001-T01; PLAN-001.
- [ ] **DEV-003-T02 · 1C** — Version and rotate a secret; observe adoption and successful reconnection before revoking the old version; restore new secret state in an isolated recovery exercise. Prerequisites: DEV-003-T01; DEV-006-T01; OPS-006-T03.
- [ ] **DEV-003-T03 · Deferred** — Assign and rotate secrets per component and report adoption for every affected component without disclosing values. Prerequisites: DEV-001-T02; DEV-003-T02.


### DEV-004 — Inspect application logs

As a developer, I want to search and follow logs from my application components,
so that I can diagnose failures and understand their behavior.

Acceptance criteria:

- I can filter logs by project, component, instance, and time range.
- Log entries include timestamps and identify their source component and instance.
- I can follow new entries and access retained logs from terminated instances.
- Access is limited to authorized projects, and the available retention window is visible.

Phase tasks:

- [ ] **DEV-004-T01 · 1C** — Collect timestamped single-component logs with project/component/instance attribution; demonstrate authorized failure diagnosis and cross-project denial. Prerequisites: OPS-004-T01; PLAN-001.
- [ ] **DEV-004-T02 · 2** — Add search, follow and project/component/instance/time filters; retrieve terminated-instance logs, show retention, and prove direct backend access cannot bypass authorization. Prerequisites: DEV-004-T01.


### DEV-005 — Inspect application resources

As a developer, I want to see my application's deployed resources and resource usage,
so that I can understand its topology and identify capacity problems.

Acceptance criteria:

- I can list deployments, instances, services, routes, and attached data services.
- I can compare CPU and memory usage with configured requests, limits, and project quotas.
- Unavailable metrics are identified explicitly, rather than displayed as zero usage.

Phase tasks:

- [ ] **DEV-005-T01 · 1C** — Expose basic authorized resource and CPU/memory observations; explicitly label missing or stale metrics. Prerequisites: OPS-004-T01; PLAN-001.
- [ ] **DEV-005-T02 · 2** — List deployments, instances, services, routes and attached data services; compare actual CPU/memory with requests, limits and quotas, including missing-data tests. Prerequisites: DEV-005-T01; OPS-003-T02; OPS-005-T01.


### DEV-006 — Track deployment health

As a developer, I want to see rollout progress and component health,
so that I know whether my application is ready to serve traffic.

Acceptance criteria:

- The platform distinguishes accepted configuration from a completed, healthy rollout.
- I can see desired and ready replica counts and the active image version for each component.
- Failed or stalled rollouts show diagnostic reasons, such as image pull or scheduling failures.

Phase tasks:

- [ ] **DEV-006-T01 · 1C** — Separate accepted desired state from observed readiness; show desired/ready counts and active image; exercise bad-image, unready, stalled and unschedulable rollout reasons. Prerequisites: PLAN-001; OPS-004-T01.
- [ ] **DEV-006-T02 · Deferred** — Report readiness, counts, active image and failures independently for each component, including mixed healthy/failed deployments. Prerequisites: DEV-001-T02; DEV-006-T01.


### DEV-007 — Recover from failed changes

As a developer, I want to retry failed deployments and restore a previous configuration,
so that I can recover from unsuccessful changes.

Acceptance criteria:

- Repeating an unchanged deployment request does not duplicate resources or delete data.
- I can select and reapply a retained application configuration revision.
- Recovery reports its rollout status and any unavailable dependencies, including old secrets.
- Restoring application configuration does not implicitly revert database contents or migrations.

Phase tasks:

- [ ] **DEV-007-T01 · 1C** — Persist operation outcomes and safe retries; interrupt after database creation, repeat the same request and prove no duplicated resources or lost data. Prerequisites: PLAN-001; DEV-010-T01.
- [ ] **DEV-007-T02 · 2** — Select/reapply retained revisions and observe recovery rollout; report missing old secrets/dependencies and prove application rollback does not revert database contents or migrations. Prerequisites: DEV-007-T01; DEV-003-T02; DEV-006-T01.


### DEV-008 — Scale application components

As a developer, I want to adjust component replicas and resource allocations,
so that I can match application capacity to demand.

Acceptance criteria:

- I can change replica counts and CPU and memory requests and limits per component.
- Changes that exceed project quotas are rejected with a clear explanation.
- If host capacity prevents scheduling, the platform shows the affected components and reason.

Phase tasks:

- [ ] **DEV-008-T01 · 2** — Change fixed replicas and CPU/memory requests/limits for one component; test explained quota rejection and host-capacity scheduling diagnostics. Prerequisites: PLAN-002; OPS-005-T02; DEV-006-T01.
- [ ] **DEV-008-T02 · Deferred** — Scale and allocate resources independently per component, retaining quota and scheduling failure attribution. Prerequisites: DEV-001-T02; DEV-008-T01.


### DEV-009 — Control application connectivity

As a developer, I want to configure public endpoints and request required outbound access,
so that users and components can reach the services they need.

Acceptance criteria:

- I can choose which components are public and see their assigned URLs and TLS status.
- Components without a public endpoint remain inaccessible through public ingress.
- Required external destinations can be declared and are subject to operator policy.
- Rejected connectivity changes explain which policy prevented them.

Phase tasks:

- [ ] **DEV-009-T01 · 2** — Implement declared public/private exposure and outbound destinations; show URLs/TLS state, explain policy denials, and verify public-to-private changes remove obsolete ingress. Prerequisites: OPS-005-T02; PLAN-001.
- [ ] **DEV-009-T02 · Deferred** — Control exposure and outbound policy per component; prove private components cannot be reached through public ingress. Prerequisites: DEV-001-T02; DEV-009-T01.


### DEV-010 — Use project data services

As a developer, I want to connect my application to a project database,
so that it can persist data without requiring database administration access.

Acceptance criteria:

- Authorized components receive connection settings through managed configuration and secrets.
- Project credentials cannot access another project's database.
- Redeploying application components preserves database contents.
- I can see data service availability and request recovery through the operator workflow.

Phase tasks:

- [ ] **DEV-010-T01 · 1C** — Bind managed database settings/secrets; demonstrate application write/read, denied cross-project database access and data preservation across redeployment. Prerequisites: PLAN-001; OPS-004-T01; OPS-001-T01.
- [ ] **DEV-010-T02 · 2** — Expose data-service availability and a tracked recovery request; demonstrate operator review, isolated/controlled restoration and developer-visible outcome without exposing foreign-project data. Prerequisites: DEV-010-T01; OPS-006-T03; DEV-006-T01.


### DEV-011 — Remove unused applications

As a developer, I want to remove applications I no longer need,
so that unused workloads stop consuming project resources.

Acceptance criteria:

- Before deletion, I can review the affected components, routes, and configuration.
- Deletion requires explicit confirmation and reports completion or partial failure.
- Persistent data is retained unless a separate, explicit data deletion is authorized.

Phase tasks:

- [ ] **DEV-011-T01 · 1C** — Preview affected workload/routes/configuration and require explicit confirmation; invalidate changed scope, retain data by default, persist retained inventory, and expose retryable partial failure and audited completion. Prerequisites: DEV-007-T01; OPS-001-T01.
- [ ] **DEV-011-T02 · Deferred** — Extend deletion previews and retryable cleanup to all components; verify actual removals match confirmed scope and data deletion remains separately authorized. Prerequisites: DEV-001-T02; DEV-011-T01.


## Operator stories

### OPS-001 — Perform security audits

As an operator, I want to review security configuration and privileged activity,
so that I can identify policy violations and investigate changes.

Acceptance criteria:

- I can inspect project permissions, workload security settings, and network policies.
- Audit records identify the actor, timestamp, action, target, and outcome of changes.
- I can filter and export records for a selected time range without exposing secret values.
- Audit retention and access restrictions are defined, and developers cannot alter audit records.

Phase tasks:

- [ ] **OPS-001-T01 · 1B** — Implement durable redacted audit records for mutations, failures and grant changes; include actor/time/action/target/result and scope/revision/operation when available; define retention/tamper protection and enforce restricted access. Prerequisites: OPS-007-T01; OPS-006-T03.
- [ ] **OPS-001-T02 · 1B** — Inspect project permissions, workload security and network policies; filter/export audit by time; prove developers cannot alter records and exports contain no secrets. Prerequisites: OPS-001-T01; OPS-004-T01.


### OPS-002 — Receive security event notifications

As an operator, I want notifications about security-relevant events,
so that I can investigate and respond promptly.

Acceptance criteria:

- I can configure alert rules for authentication failures, access denials, and privileged changes.
- Notifications include severity, time, affected resources, and a reference to supporting events.
- I can configure and test a notification destination and see delivery failures.
- Repeated events are grouped to reduce duplicate notifications without hiding ongoing incidents.

Phase tasks:

- [ ] **OPS-002-T01 · 1B** — Configure authentication-failure, denial and privileged-change rules; link severity/time/resources to supporting events; test destinations, delivery-failure visibility and grouping that preserves ongoing incidents. Prerequisites: OPS-001-T01; OPS-007-T01.


### OPS-003 — Monitor platform capacity

As an operator, I want an overview of platform resource usage and allocation,
so that I can identify bottlenecks and plan capacity.

Acceptance criteria:

- I can compare host capacity, actual CPU and memory usage, and workload resource requests.
- I can inspect storage usage and break down workload usage by project.
- Shared services are included in the overview, and missing or stale metrics are identified.
- Capacity thresholds can trigger alerts, and unschedulable workloads are visible.

Phase tasks:

- [ ] **OPS-003-T01 · 1C** — Measure host, shared-service, workload and storage consumption; record system reserve and representative load baseline without promising unmeasured capacity. Prerequisites: PLAN-001.
- [ ] **OPS-003-T02 · 2** — Deliver host/usage/request comparisons and project storage/usage breakdown including shared services; test stale/missing metrics, capacity alerts and unschedulable workload visibility. Prerequisites: OPS-003-T01.


### OPS-004 — Manage identities and project access

As an operator, I want to assign and revoke project permissions,
so that users can manage only the resources they are authorized to access.

Acceptance criteria:

- Developers authenticate with individual identities without using the platform admin token.
- Permissions distinguish viewing resources, changing applications, and administering the platform.
- Authorization is enforced for every project operation, including logs, metrics, and secrets.
- Revoking access blocks subsequent requests and creates an audit record.

Phase tasks:

- [ ] **OPS-004-T01 · 1B** — Implement individual identities and scoped view/change/admin roles; deny unauthorized operations, revoke a platform grant and prove the next request is denied and audited. Release with audit, never with a developer admin-token fallback. Prerequisites: OPS-001-T01.


### OPS-005 — Enforce project policies and quotas

As an operator, I want to define resource and security constraints per project,
so that workloads operate within the platform's agreed boundaries.

Acceptance criteria:

- I can configure project quotas, default resource limits, and allowed network access.
- Workloads that violate required security settings are rejected with a specific reason.
- Policy changes show their effect on existing workloads and subsequent deployments.
- Project quotas are considered alongside host capacity when admitting new workloads.

Phase tasks:

- [ ] **OPS-005-T01 · 2** — Configure per-project quotas, resource defaults and allowed network/security policy; show impact on existing workloads and subsequent deployments. Prerequisites: PLAN-002; OPS-004-T01; OPS-003-T01.
- [ ] **OPS-005-T02 · 2** — Reject security/quota violations with specific reasons; admit against aggregate host allocations after system/shared-service reserve and test policy enforcement. Prerequisites: OPS-005-T01; OPS-003-T02.


### OPS-006 — Back up and restore platform data

As an operator, I want scheduled backups and a verified restoration procedure,
so that I can recover project data and platform configuration after a failure.

Acceptance criteria:

- Backup scope includes project databases, platform state, and configuration and secrets needed for recovery.
- Backup schedules, retention, access controls, and storage outside the host are configured.
- Failed or overdue backups trigger notifications.
- A restoration exercise verifies data and application access against documented recovery time and data loss targets.

Phase tasks:

- [ ] **OPS-006-T01 · 1A** — Inventory databases, roles, state, config, secrets and service-state recovery needs; record storage, encryption/key recovery, schedule, retention/access, RPO/RTO and replacement-host decisions. Prerequisites: Installation inventory and operator-selected storage/targets.
- [ ] **OPS-006-T02 · 1A** — Automate bounded non-overlapping scheduled capture, encryption, off-host transfer and verified readback; test failure/overdue/stalled/missing signals independently of heartbeat, retention and access controls; failed uploads never advance success time. Prerequisites: OPS-006-T01; OPS-007-T01.
- [ ] **OPS-006-T03 · 1A** — Recover onto an empty isolated installation without the original host; verify data/permissions/workloads/ingress/monitoring and actual alert receipt against RPO/RTO; exercise unavailable/corrupt backup and key failures; record recurring exercise schedule. Prerequisites: OPS-006-T02.


### OPS-007 — Monitor service availability

As an operator, I want to monitor shared services and application availability,
so that I can detect outages and identify affected projects.

Acceptance criteria:

- Health checks cover the control plane, ingress, database, and monitoring services.
- Alerts identify the failing service and affected projects where that information is available.
- An external check can report a complete host outage when local monitoring is unavailable.
- Alert routing can be tested before relying on it for incident response.

Phase tasks:

- [ ] **OPS-007-T01 · 1A** — Configure real Alertmanager/watchdog routing and response ownership; verify actual outage/recovery receipt and delivery failures, cluster/host expiry, public canary and independent watchdog cron/hosting detection. Keep platform, pipeline and backup identities/timestamps isolated. Prerequisites: Installation inventory and notification recipients.
- [ ] **OPS-007-T02 · 2** — Exercise control-plane, ingress, database, monitoring and application failure checks; identify affected projects where known and verify external detection with host/local monitoring unavailable. Prerequisites: OPS-007-T01; DEV-006-T01.


### OPS-008 — Decommission projects safely

As an operator, I want to retire projects with an explicit data retention decision,
so that I can reclaim resources without accidentally deleting required data.

Acceptance criteria:

- A deletion preview lists workloads, routes, credentials, databases, and retained backups.
- Destructive data deletion requires explicit confirmation of the project and retention decision.
- Decommissioning revokes project access and credentials and removes the selected resources.
- Partial failures can be retried, and the result and retained resources are recorded in the audit trail.

Phase tasks:

- [ ] **OPS-008-T01 · 2** — Preview project workloads/routes/credentials/databases/backups; record explicit project-specific retention/deletion decisions and confirmation invalidated by scope changes. Prerequisites: DEV-011-T01; OPS-004-T01; OPS-006-T03.
- [ ] **OPS-008-T02 · 2** — Revoke project access/credentials and remove selected resources; inject partial failures, retry without affecting other projects, and audit all retained/deleted resources and outcomes. Prerequisites: OPS-008-T01; OPS-001-T01.

## Additional phase tasks

These tasks make the existing phase work executable without inventing new DEV/OPS stories or treating portability, interfaces or AI as acceptance criteria for unrelated stories. They are mandatory within their assigned phase. An unresolved ADR may block implementation choices; it does not waive a requirement or permit phase closure without its acceptance evidence. An explicit scope change must update the requirements and phase plan together. Deferred component implementation remains separate.

- [ ] **PLAN-001 · 1C** — Implement stable project/environment/application identity and atomically persisted desired revisions/asynchronous jobs before side effects, returning an operation ID with authorized progress and worker-interruption recovery. Validate the supported single-image profile, reject unknown fields/unsupported capabilities before side effects, and use technology-independent public identities and minimal provider ports. Demonstrate an authorized application restart with unchanged desired spec, retained data and observed readiness; demonstrate minimal API/CLI deployment and record installation versions/parameters. Prerequisites: Phase 1B gate.
- [ ] **PLAN-002 · 2** — Complete ApplicationSpec/API fit-gap and schema reuse assessment, versioned OpenAPI contract, environment capabilities/profiles, explicit CPU/memory request/limit semantics and migration rules; reject unsupported requests before side effects and keep backend fields out of the public contract. Prerequisites: Phase 1 gate.
- [ ] **PLAN-003 · 2** — Harden worker interruption, concurrent writes, revision retention and drift recovery; prove no duplicated resources/lost revisions and redacted traceable provider failures. Prerequisites: PLAN-002; DEV-007-T02.
- [ ] **PLAN-004 · 2** — Add the Docker adapter and shared provider contract tests; deploy/update/observe/remove the same spec on Kubernetes and Docker, including partial failure and capability rejection; publish tested profile differences. Prerequisites: PLAN-002; PLAN-003; Phase 2 retained-backlog packages.
- [ ] **PLAN-005 · 2** — Record ADR-006 language decision; if migration is selected, create separately gated parity/state-migration tasks before execution. A decision alone does not prove migration complete. Prerequisites: Code/effort analysis before contract stabilization.
- [ ] **PLAN-006 · 3** — Deliver portal and CLI using the same API for ownership/roles, applications, deployments, redacted config, logs and operations; diagnose an injected failure and prove bypassed UI checks still fail server-side. Prerequisites: Phase 2 gate.
- [ ] **PLAN-007 · 3** — Deliver the web/PostgreSQL template and reproducible create/deploy/diagnose journey; verify UI/API compatibility and document the role matrix. Prerequisites: PLAN-006.
- [ ] **PLAN-008 · 3** — Deliver separate authorized/audited human database identity and controlled tunnel; test foreign-project denial, credentials distinct from application credentials, and revocation of new/existing sessions per policy. Prerequisites: Phase 2 gate; accepted IAM design.
- [ ] **PLAN-009 · 3** — Automate hosted-application OIDC clients/redirect URIs; demonstrate platform/application role separation and no implicit platform-admin access. Record the blocking decision while the implementation choice remains open; F-10 acceptance is still required for Phase 3 completion. Prerequisites: Phase 2 gate; ADR-004 acceptance.
- [ ] **PLAN-010 · 4.1** — Expose bounded read-only Platform API tools and authorized/redacted application/revision/configuration/document context; produce sourced explanations and test project denial and untrusted-input handling. Prerequisites: Phase 3 gate; scoped data/audit evidence.
- [ ] **PLAN-011 · 4.2** — Correlate incident logs, metrics and history with timestamps/comparison windows; distinguish observations/hypotheses and explicitly report missing evidence. Prerequisites: PLAN-010; DEV-004-T02; DEV-005-T02; DEV-007-T02.
- [ ] **PLAN-012 · 4.3** — Implement read-only investigation with tool budgets/errors; evaluate bad database host, pool exhaustion, resource pressure and insufficient evidence for diagnosis, abstention, unnecessary calls and time/cost; test injection and secret/project boundaries. Prerequisites: PLAN-011.
- [ ] **PLAN-013 · 4.4** — Generate a reviewable configuration/deployment diff bound to target and revision, with supporting evidence and a rollback plan; do not execute it at this stage. Prerequisites: PLAN-012.
- [ ] **PLAN-014 · 4.5** — Apply only an exactly approved diff through authorized Platform API calls; reject stale approvals, audit execution and verify observed health/metrics. Demonstrate regression, investigation, approval and recovery in test resources. Prerequisites: PLAN-013; DEV-007-T02; OPS-001-T01.
- [ ] **PLAN-015 · 4 (after 4.5)** — Demonstrate development assistance grounded in authorized docs, ADRs, contracts and repository context: template selection, change impact or review with runtime evidence; retain source references and project/secret boundaries. Prerequisites: PLAN-014.
