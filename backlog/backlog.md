# Developer platform user stories

This backlog describes desired capabilities, not implementation status. Some
capabilities already have a foundation in the platform; others require new work.
See the [platform overview](../README.md) for current features and limitations.

See [implementation status](implementation-status.md) for current story coverage
and the [implementation plan](implementation-plan.md) for priorities and milestones.

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

## Developer stories

### DEV-001 — Deploy applications with multiple components

As a developer, I want to deploy an application composed of multiple components,
so that I can run its services and workers together within one project.

Acceptance criteria:

- Each component can specify its own image, startup command, ports, and replica count.
- Components can communicate through stable internal service names within the project.
- Deployment results identify successful and failed components and explain failures.
- Updating one component does not require redeploying unchanged components.

### DEV-002 — Configure application environments

As a developer, I want to manage non-secret environment variables for each component,
so that I can change application behavior without rebuilding its image.

Acceptance criteria:

- I can view, add, update, and remove variables for an authorized component.
- Invalid configuration is rejected with an actionable error before it is applied.
- Changes indicate whether a rollout is needed and when the new configuration is active.

### DEV-003 — Manage application secrets

As a developer, I want to manage secret environment variables separately from ordinary
configuration, so that applications can use credentials without exposing them.

Acceptance criteria:

- I can create, replace, and remove secrets and assign them to specific components.
- Stored values are not returned in ordinary configuration views, logs, or audit records.
- Unauthorized users cannot read or modify secrets.
- I can roll out a replacement secret and see which components have adopted it.

### DEV-004 — Inspect application logs

As a developer, I want to search and follow logs from my application components,
so that I can diagnose failures and understand their behavior.

Acceptance criteria:

- I can filter logs by project, component, instance, and time range.
- Log entries include timestamps and identify their source component and instance.
- I can follow new entries and access retained logs from terminated instances.
- Access is limited to authorized projects, and the available retention window is visible.

### DEV-005 — Inspect application resources

As a developer, I want to see my application's deployed resources and resource usage,
so that I can understand its topology and identify capacity problems.

Acceptance criteria:

- I can list deployments, instances, services, routes, and attached data services.
- I can compare CPU and memory usage with configured requests, limits, and project quotas.
- Unavailable metrics are identified explicitly, rather than displayed as zero usage.

### DEV-006 — Track deployment health

As a developer, I want to see rollout progress and component health,
so that I know whether my application is ready to serve traffic.

Acceptance criteria:

- The platform distinguishes accepted configuration from a completed, healthy rollout.
- I can see desired and ready replica counts and the active image version for each component.
- Failed or stalled rollouts show diagnostic reasons, such as image pull or scheduling failures.

### DEV-007 — Recover from failed changes

As a developer, I want to retry failed deployments and restore a previous configuration,
so that I can recover from unsuccessful changes.

Acceptance criteria:

- Repeating an unchanged deployment request does not duplicate resources or delete data.
- I can select and reapply a retained application configuration revision.
- Recovery reports its rollout status and any unavailable dependencies, including old secrets.
- Restoring application configuration does not implicitly revert database contents or migrations.

### DEV-008 — Scale application components

As a developer, I want to adjust component replicas and resource allocations,
so that I can match application capacity to demand.

Acceptance criteria:

- I can change replica counts and CPU and memory requests and limits per component.
- Changes that exceed project quotas are rejected with a clear explanation.
- If host capacity prevents scheduling, the platform shows the affected components and reason.

### DEV-009 — Control application connectivity

As a developer, I want to configure public endpoints and request required outbound access,
so that users and components can reach the services they need.

Acceptance criteria:

- I can choose which components are public and see their assigned URLs and TLS status.
- Components without a public endpoint remain inaccessible through public ingress.
- Required external destinations can be declared and are subject to operator policy.
- Rejected connectivity changes explain which policy prevented them.

### DEV-010 — Use project data services

As a developer, I want to connect my application to a project database,
so that it can persist data without requiring database administration access.

Acceptance criteria:

- Authorized components receive connection settings through managed configuration and secrets.
- Project credentials cannot access another project's database.
- Redeploying application components preserves database contents.
- I can see data service availability and request recovery through the operator workflow.

### DEV-011 — Remove unused applications

As a developer, I want to remove applications I no longer need,
so that unused workloads stop consuming project resources.

Acceptance criteria:

- Before deletion, I can review the affected components, routes, and configuration.
- Deletion requires explicit confirmation and reports completion or partial failure.
- Persistent data is retained unless a separate, explicit data deletion is authorized.

## Operator stories

### OPS-001 — Perform security audits

As an operator, I want to review security configuration and privileged activity,
so that I can identify policy violations and investigate changes.

Acceptance criteria:

- I can inspect project permissions, workload security settings, and network policies.
- Audit records identify the actor, timestamp, action, target, and outcome of changes.
- I can filter and export records for a selected time range without exposing secret values.
- Audit retention and access restrictions are defined, and developers cannot alter audit records.

### OPS-002 — Receive security event notifications

As an operator, I want notifications about security-relevant events,
so that I can investigate and respond promptly.

Acceptance criteria:

- I can configure alert rules for authentication failures, access denials, and privileged changes.
- Notifications include severity, time, affected resources, and a reference to supporting events.
- I can configure and test a notification destination and see delivery failures.
- Repeated events are grouped to reduce duplicate notifications without hiding ongoing incidents.

### OPS-003 — Monitor platform capacity

As an operator, I want an overview of platform resource usage and allocation,
so that I can identify bottlenecks and plan capacity.

Acceptance criteria:

- I can compare host capacity, actual CPU and memory usage, and workload resource requests.
- I can inspect storage usage and break down workload usage by project.
- Shared services are included in the overview, and missing or stale metrics are identified.
- Capacity thresholds can trigger alerts, and unschedulable workloads are visible.

### OPS-004 — Manage identities and project access

As an operator, I want to assign and revoke project permissions,
so that users can manage only the resources they are authorized to access.

Acceptance criteria:

- Developers authenticate with individual identities without using the platform admin token.
- Permissions distinguish viewing resources, changing applications, and administering the platform.
- Authorization is enforced for every project operation, including logs, metrics, and secrets.
- Revoking access blocks subsequent requests and creates an audit record.

### OPS-005 — Enforce project policies and quotas

As an operator, I want to define resource and security constraints per project,
so that workloads operate within the platform's agreed boundaries.

Acceptance criteria:

- I can configure project quotas, default resource limits, and allowed network access.
- Workloads that violate required security settings are rejected with a specific reason.
- Policy changes show their effect on existing workloads and subsequent deployments.
- Project quotas are considered alongside host capacity when admitting new workloads.

### OPS-006 — Back up and restore platform data

As an operator, I want scheduled backups and a verified restoration procedure,
so that I can recover project data and platform configuration after a failure.

Acceptance criteria:

- Backup scope includes project databases, platform state, and configuration and secrets needed for recovery.
- Backup schedules, retention, access controls, and storage outside the host are configured.
- Failed or overdue backups trigger notifications.
- A restoration exercise verifies data and application access against documented recovery time and data loss targets.

### OPS-007 — Monitor service availability

As an operator, I want to monitor shared services and application availability,
so that I can detect outages and identify affected projects.

Acceptance criteria:

- Health checks cover the control plane, ingress, database, and monitoring services.
- Alerts identify the failing service and affected projects where that information is available.
- An external check can report a complete host outage when local monitoring is unavailable.
- Alert routing can be tested before relying on it for incident response.

### OPS-008 — Decommission projects safely

As an operator, I want to retire projects with an explicit data retention decision,
so that I can reclaim resources without accidentally deleting required data.

Acceptance criteria:

- A deletion preview lists workloads, routes, credentials, databases, and retained backups.
- Destructive data deletion requires explicit confirmation of the project and retention decision.
- Decommissioning revokes project access and credentials and removes the selected resources.
- Partial failures can be retried, and the result and retained resources are recorded in the audit trail.
