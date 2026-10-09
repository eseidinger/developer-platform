# ADR-006 – Polyglot Service Responsibilities

Created: September 25, 2026. Accepted as target direction: October 1, 2026. Scope amended: October 4, 2026. Status: **Deferred to optional Phase 5; one Python/FastAPI application is the selected current architecture**.

## Context

The platform uses one Python/FastAPI process for application records, request coordination, authorization, durable operations, PostgreSQL provisioning, and Kubernetes application. The implementation now includes scoped grants, immutable revisions, and resumable queued operations. It has no provider-interface layer or separately deployed catalog, control-plane, and worker services.

Earlier planning proposed separate technology homes for business metadata, runtime coordination, and infrastructure automation. The operational cost and product value of that split have not been demonstrated. Clear internal ownership remains necessary, but deployable service boundaries are optional.

## Considered options

| Option | Benefit | Cost/risk |
|---|---|---|
| Continue with Python | Existing automation and rapid development | Deliberately enforce typing, domain boundaries, and workflow robustness |
| Quarkus core | Java reference architecture and typed domain | Rewrite, migration, and parity verification |
| Quarkus plus Python worker | Domain core and specialized automation | Additional operational, authentication, and distributed-workflow complexity |
| Kotlin catalog, Quarkus control plane, Python workers | Clear business-data, runtime-policy, and infrastructure-execution ownership | Three deployables/contracts, cross-service authorization, migration, and operational overhead |

## Amended decision

Keep application metadata, grants, deployment intent, operations, policy, runtime observation, and infrastructure execution in one Python/FastAPI application through Phases 2 to 4. Preserve logical module boundaries and durable operation semantics inside the codebase, but do not create separately deployed catalog, control-plane, or worker services in the current scope.

If a recorded operational or product need activates optional Phase 5, the following allocation remains a candidate rather than a required end state:

- **Kotlin + Spring Boot Application Catalog:** authoritative application identity, owners, repositories, environments, dependencies, grants, and intended resource relationships.
- **Java + Quarkus Platform API / Control Plane:** authoritative desired deployment revisions, policy and capability validation, operation lifecycle, provider assignments, runtime status, and platform events.
- **Python automation and operations:** idempotent infrastructure execution, observation, diagnostics, backup/audit integrations, and future AI-assisted operational analysis.

Under that optional allocation, the control plane decides and records what approved operation should happen, Python workers execute bounded provider steps, and the catalog supplies application and permission facts. State-changing AI actions still use the normal authorization and operation path.

Services exchange stable identifiers, versioned desired specifications, job envelopes/results, and events. They own separate data stores or schemas and do not read one another's tables. A catalog deployment summary is a projection; control-plane operation and runtime state remain authoritative.

## Optional transition constraints

Preserve the working Python platform unless an explicit Phase 5 scope decision identifies a justified extraction. Any selected extraction is not a big-bang rewrite: establish the relevant contract first, then migrate ownership with versioned data migration, reconciliation, rollback, and credential separation.

Before moving traffic in an activated Phase 5 extraction, verify API behavior, authorization at every new service boundary, operation resumption, metadata and operation migration, audit correlation, observability, backup/restore coverage, and rollback. Run a single writer for each authoritative record during transition and avoid indefinite dual writes. Until then, the FastAPI application remains the permanent current path and new code respects internal ownership seams without introducing remote-service contracts.

Implementation language does not change ApplicationSpec. A mixed-language architecture is justified only if independently deploying a responsibility delivers measurable value greater than its operational and distributed-system cost.

## Consequences

The current platform retains a single deployment, process-level calls, one operational lifecycle, and the existing Python implementation. It must maintain explicit internal responsibility boundaries through modules, state ownership, tests, and versioned public contracts.

Activating the optional split would add deployments, versioned inter-service contracts, failure modes, service identities, tracing, and operational cost. Those costs require separate acceptance and cannot be justified by technology variety alone.

The [technology roles reference](../../maintainers/delivery/history/technology-roles.md) records the current Python responsibility model and the optional candidate allocation. Any extraction is planned only through [optional Phase 5](../evolution.md). The earlier acceptance of a target split does not authorize implementation in the current phases.
