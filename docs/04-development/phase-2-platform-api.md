# Phase 2 – Stable Contract and Provider Portability

Status: planned. Covers [F-07 and Phase 2 extensions of F-01 through F-06, F-08, and N-01 through N-08](../01-product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](delivery-backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Evolve the working hybrid path into a reliable control plane and execute the same use case directly on Docker.

## Work packages

1. Compare the actual API with [ApplicationSpec](../02-architecture/application-spec.md); implement the schema, OpenAPI contract, and versioning rules, including explicit request/limit resource semantics needed by scaling and policy tasks.
2. Model capabilities and service profiles per environment. Remove backend-specific fields from the public contract.
3. Harden persistent jobs, revisions, concurrent updates, retries, drift handling, and deletion plans.
4. Add a Docker adapter alongside Kubernetes; reuse database and observability providers.
5. Build provider contract tests and integration tests for partial failures.
6. Decide [ADR-006](../03-decisions/ADR-006-python-quarkus-evolution.md) after code analysis. If migration is chosen, treat parity and state migration as separate work packages.
7. Complete the fit-gap assessment in the [ADR index](../03-decisions/README.md) before stabilizing the schema.

## Retained backlog packages before provider acceptance

Phase 1 supplies durable operations, scoped access/audit, basic diagnostics, protected backups and confirmed single-application removal. These packages complete the retained single-image workflows using the [delivery backlog](delivery-backlog.md); component-specific extensions remain deferred as recorded in the [plan](development-plan.md#backlog-delivery-commitments).

1. **Diagnostics and capacity (DEV-004/005, OPS-003/007):** search/follow authorized logs by project, component, instance and time, including terminated instances with visible retention. Prevent direct backend access from bypassing scope. Inventory deployments, instances, services, routes and data attachments. Compare actual CPU/memory against requests, limits, quotas and host capacity; include shared services, project storage, stale/missing metrics, capacity alerts and unschedulable workloads. Exercise control-plane, ingress, database, monitoring and application outages with affected-project context where available; prove external detection during total host failure.
2. **Policy, scaling and connectivity (DEV-008/009, OPS-005):** offer operator-managed quotas, resource defaults, workload security and allowed network access. Preview effects on existing workloads and subsequent admission. Check aggregate requests against usable host capacity after shared-service/system reserves. Accept replica and CPU/memory request/limit changes; reject quota/security violations with specific reasons and report scheduling failures. Declare permitted outbound destinations, public/private endpoints, URLs and TLS state; verify policy denials and removal of old public routes during exposure changes.
3. **Revision and data-service recovery (DEV-007/010):** select/reapply retained revisions, detect missing secret versions and other unavailable dependencies, and observe recovery rollout. Application rollback never reverts database contents or migrations. Show data-service availability and provide a tracked developer recovery request that an operator reviews, executes through the verified restore procedure and reports back on. Test preservation and cross-project denial.
4. **Project retirement (OPS-008):** after resumable application deletion works, preview all project workloads, routes, credentials, databases and retained backups. Require project-specific retention/deletion decisions and explicit destructive confirmation; changed scope invalidates confirmation. Revoke access/credentials, remove only selected resources, and audit every retained/deleted resource. Inject partial failure and prove retries cannot touch another project.

Include new revisions, jobs, audit, identities, secrets and retention inventories in the recovery scope and repeat the isolated restore gate. Recheck all authorization and audit boundaries. Complete these outcomes on the hybrid provider before declaring second-provider acceptance; adapter development may proceed in parallel.

## Acceptance

Deploy, update, observe, and remove the same portable application in two environments. Unsupported capabilities produce clear errors before side effects. Worker interruption and concurrent updates cause neither duplicate resources nor lost revisions.

Every retained backlog package above must have criterion-level evidence, including denied access, failure injection and retained-data checks. No deferred multi-component story closes through these single-image tests.

Provider failure leaves the job in a traceable state; recovery observes existing resources. Public errors do not expose provider credentials.

## Outcome

A versioned core contract, a published capability matrix for actually tested profiles, and documented differences. Demonstrate portability by execution, not merely by implementing two interfaces.
