# Phase 2C – Platform Capabilities

Status: **accepted October 5, 2026**. Covers the remaining Phase 2 extensions of F-01 through F-06, F-08, F-13, F-14, and N-01 through N-08 in the [requirements](../01-product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](delivery-backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Complete the developer and operator lifecycle on the existing hybrid infrastructure: one Python/FastAPI Platform API and the existing Kubernetes/k3d workload provider. Phase 2C does not add a compute adapter or split the API into separately deployed catalog, control-plane, and worker services.

The public contract remains expressed in platform concepts and keeps Kubernetes implementation details out of client payloads. That contract discipline supports clients and future evolution without requiring provider parity now.

## Work packages

1. Carry forward the accepted named/scheduled-component schema from Phase 2A and machine-identity/grant contract from Phase 2B. Maintain the versioned OpenAPI contract, capability reporting, explicit resource semantics, and rejection before side effects.
2. **Diagnostics and capacity (DEV-004/005, OPS-003/007):** search and follow authorized logs by project, component, instance, and time, including terminated instances with visible retention. Inventory deployed resources and data attachments. Compare actual CPU/memory with requests, limits, quotas, and host capacity; exercise current platform failure signals with affected-project context.
3. **Policy, scaling, and connectivity (DEV-008/009, OPS-005):** manage quotas, resource defaults, workload security, replica/resource changes, public/private endpoints, and allowed network access. Preview effects and reject policy or capacity violations with specific reasons.
4. **Revision and data-service recovery (DEV-007/010):** reapply retained revisions, report unavailable dependencies, observe recovery rollouts, and expose tracked operator recovery requests. Application rollback must not revert database contents or migrations.
5. **Project retirement (OPS-008):** preview workloads, routes, credentials, databases, and retained backups; require explicit project-specific retention/deletion decisions; revoke access and remove selected resources safely and audibly.
6. Continue hardening persistent operations, revisions, concurrent updates, retries, drift handling, and deletion plans inside the Python application.

Include new revisions, operations, audit records, identities, secrets, and retention inventories in recovery scope. Under [ADR-016](../03-decisions/ADR-016-phase-1a-recovery-scope.md), isolated recovery exercises remain outside current delivery gates unless explicitly rescheduled. Recheck authorization and audit boundaries for every new endpoint and data surface.

## Acceptance

Through the single Python API and Kubernetes provider, an authorized human or machine identity can create, deploy, update, observe, recover, and retire applications with clear capability, policy, and failure behavior. Unsupported capabilities are rejected before side effects. Interrupted work and concurrent updates cause neither duplicate resources nor lost revisions.

Each work package has criterion-level evidence for success, denial, failure injection, and retained-data behavior. Phase 2A multi-service/scheduled-component tests and Phase 2B machine-credential tests remain applicable and are rerun where Phase 2C changes their surfaces.

Phase 2C acceptance is recorded in EV-39 through EV-44 in the
[delivery backlog](delivery-backlog.md#verification-register). The owner accepted the
remaining lab-specific boundaries (single-host k3d capacity calibration, best-effort
Kubernetes log retention, and retained-data rather than destructive-data deletion) as
documented limits of this phase; they are not production-capacity or hostile-tenant
claims.

Provider failures remain traceable and recoverable by observing existing resources. Public errors, logs, status, audit data, and inventories do not expose provider credentials, client secrets, or bearer tokens.

## Outcome

A complete platform lifecycle on the selected infrastructure, delivered and operated as one Python API application. Additional compute providers and deployable service extraction are explicitly outside Phase 2C; see [optional Phase 5](phase-5-optional-architecture-expansion.md).
