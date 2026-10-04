# Phase 2C – Stable Contract and Provider Portability

Status: planned after [Phase 2B](phase-2b-ci-deployment-credentials.md). Covers [F-07 and Phase 2 extensions of F-01 through F-06, F-08, F-13, F-14, and N-01 through N-08](../01-product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](delivery-backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Evolve the accepted Phase 2A multi-service and Phase 2B machine-credential paths into a Kotlin/Spring application catalog, Quarkus control plane, and Python automation workers, then execute the portable contract directly on Docker.

## Work packages

1. Carry forward the accepted named/scheduled-component schema and migration from Phase 2A and the CI machine-identity/grant contract from Phase 2B; complete the [ApplicationSpec](../02-architecture/application-spec.md), OpenAPI contract, and versioning rules, including explicit request/limit resource semantics needed by scaling and policy tasks.
2. Model capabilities and service profiles per environment. Remove backend-specific fields from the public contract.
3. Define versioned Catalog ↔ Control Plane and Control Plane ↔ Python worker contracts, including stable IDs, permission/catalog versions, immutable job envelopes, structured results, events, idempotency, redaction, and correlation IDs.
4. Extract the Kotlin/Spring Application Catalog. Migrate application metadata and grants with reconciliation, authorization parity, backup/restore, a single-writer cutover, and a tested rollback path.
5. Implement the Quarkus control plane and migrate desired revisions, jobs, runtime state, policy, and events. Pass public-contract and behavior parity for success, denial, conflict, partial failure, resume, audit, and rollback before routing traffic to it.
6. Separate Python workers behind durable dispatch. Use scoped provider credentials and prove safe interruption, duplicate delivery, stale authorization handling, timeout observation, and result redaction.
7. Harden persistent jobs, revisions, concurrent updates, retries, drift handling, and deletion plans.
8. Add a Docker adapter alongside Kubernetes; reuse database and observability provider contracts implemented by Python workers.
9. Build catalog, control-plane, worker, provider, and end-to-end contract tests for partial failures and unavailable dependencies.
10. Complete the fit-gap assessment in the [ADR index](../03-decisions/README.md) before stabilizing the schema.

## Retained backlog packages before provider acceptance

Phase 1 supplies durable operations, scoped access/audit, basic diagnostics, protected backups and confirmed single-application removal. Phase 2A expands that baseline to named long-running and scheduled components, and Phase 2B adds revocable CI machine credentials. These packages complete the retained workflows using the [delivery backlog](delivery-backlog.md) and must operate on every relevant component and principal type.

1. **Diagnostics and capacity (DEV-004/005, OPS-003/007):** search/follow authorized logs by project, component, instance and time, including terminated instances with visible retention. Prevent direct backend access from bypassing scope. Inventory deployments, instances, services, routes and data attachments. Compare actual CPU/memory against requests, limits, quotas and host capacity; include shared services, project storage, stale/missing metrics, capacity alerts and unschedulable workloads. Exercise control-plane, ingress, database, monitoring and application outages with affected-project context where available; prove external detection during total host failure.
2. **Policy, scaling and connectivity (DEV-008/009, OPS-005):** offer operator-managed quotas, resource defaults, workload security and allowed network access. Preview effects on existing workloads and subsequent admission. Check aggregate requests against usable host capacity after shared-service/system reserves. Accept replica and CPU/memory request/limit changes; reject quota/security violations with specific reasons and report scheduling failures. Declare permitted outbound destinations, public/private endpoints, URLs and TLS state; verify policy denials and removal of old public routes during exposure changes.
3. **Revision and data-service recovery (DEV-007/010):** select/reapply retained revisions, detect missing secret versions and other unavailable dependencies, and observe recovery rollout. Application rollback never reverts database contents or migrations. Show data-service availability and provide a tracked developer recovery request that an operator reviews, executes through the verified restore procedure and reports back on. Test preservation and cross-project denial.
4. **Project retirement (OPS-008):** after resumable application deletion works, preview all project workloads, routes, credentials, databases and retained backups. Require project-specific retention/deletion decisions and explicit destructive confirmation; changed scope invalidates confirmation. Revoke access/credentials, remove only selected resources, and audit every retained/deleted resource. Inject partial failure and prove retries cannot touch another project.

Include new revisions, jobs, audit, identities, secrets and retention inventories in the recovery scope. Under [ADR-016](../03-decisions/ADR-016-phase-1a-recovery-scope.md), isolated recovery exercises remain outside the current delivery gates unless explicitly rescheduled; in-place checks do not establish them. Recheck all authorization and audit boundaries. Complete these outcomes on the hybrid provider before declaring second-provider acceptance; adapter development may proceed in parallel.

## Acceptance

Create and authorize an application through the catalog; deploy, update, observe, and remove the same portable application through the control plane in two environments. Unsupported capabilities produce clear errors before side effects. Worker interruption and concurrent updates cause neither duplicate resources nor lost revisions.

Cross-service acceptance traces a request from actor and catalog/grant version through desired revision, operation, Python job, provider resources, result, and event. Catalog or worker unavailability produces bounded, visible behavior. No service reads another service's tables, and cutover/rollback preserves stable IDs and authoritative state.

Every retained backlog package above must have criterion-level evidence, including denied access, failure injection and retained-data checks. Phase 2A and Phase 2B evidence are prerequisites; provider acceptance must rerun the relevant multi-service, scheduled-component, and machine-credential authorization tests rather than relying on the original Kubernetes/Keycloak-only results.

Provider failure leaves the job in a traceable state; recovery observes existing resources. Public errors do not expose provider credentials.

## Outcome

A versioned core contract, a published capability matrix for actually tested profiles, and documented differences. Demonstrate portability by execution, not merely by implementing two interfaces.
