# ADR-006 – Polyglot Service Responsibilities

Created: September 25, 2026. Accepted: October 1, 2026. Status: **Accepted target direction; implementation pending**.

## Context

The initial implementation uses one Python/FastAPI process for application records, request coordination, PostgreSQL provisioning, and Kubernetes application. The source review established that this remains the implementation baseline and lacks durable jobs, provider ports, scoped authorization, and revision history.

The platform needs an explicit home for business-oriented application metadata, a typed runtime control plane, and integration-heavy infrastructure automation. The split must preserve the technology-independent public contract and cannot turn framework adoption into evidence of functional parity.

## Considered options

| Option | Benefit | Cost/risk |
|---|---|---|
| Continue with Python | Existing automation and rapid development | Deliberately enforce typing, domain boundaries, and workflow robustness |
| Quarkus core | Java reference architecture and typed domain | Rewrite, migration, and parity verification |
| Quarkus plus Python worker | Domain core and specialized automation | Additional operational, authentication, and distributed-workflow complexity |
| Kotlin catalog, Quarkus control plane, Python workers | Clear business-data, runtime-policy, and infrastructure-execution ownership | Three deployables/contracts, cross-service authorization, migration, and operational overhead |

## Decision

Adopt these target technology roles:

- **Kotlin + Spring Boot Application Catalog:** authoritative application identity, owners, repositories, environments, dependencies, grants, and intended resource relationships.
- **Java + Quarkus Platform API / Control Plane:** authoritative desired deployment revisions, policy and capability validation, operation lifecycle, provider assignments, runtime status, and platform events.
- **Python automation and operations:** idempotent infrastructure execution, observation, diagnostics, backup/audit integrations, and future AI-assisted operational analysis.

The control plane decides and records what approved operation should happen. Python workers decide how to execute its bounded provider steps and return structured results. The catalog supplies application and permission facts but does not deploy. State-changing AI actions use the control plane's normal authorization and operation path.

Services exchange stable identifiers, versioned desired specifications, job envelopes/results, and events. They own separate data stores or schemas and do not read one another's tables. A catalog deployment summary is a projection; control-plane operation and runtime state remain authoritative.

## Transition constraints

Preserve the working Python vertical slice until replacements pass contract and behavior parity. The target is not a big-bang rewrite. Establish catalog, control-plane, and worker contracts first; then migrate ownership with versioned data migration, reconciliation, rollback, and credential separation.

Before moving traffic, verify API behavior, authorization at every service boundary, job resumption, metadata and operation migration, provider parity, audit correlation, observability, backup/restore coverage, and rollback. Run a single writer for each authoritative record during transition; avoid indefinite dual writes. The existing FastAPI service may temporarily implement multiple logical roles, but new code must respect the target ownership seams.

Implementation language does not change ApplicationSpec or provider domain boundaries. A mixed-language architecture is justified only if clear responsibilities deliver measurable value.

## Consequences

The platform gains explicit responsibility boundaries and can use each ecosystem where it fits. It also accepts more deployments, versioned contracts, failure modes, service identities, tracing, and operational cost. Catalog availability affects new control-plane acceptance; already accepted operations retain the immutable authorization and catalog context required for safe resumption, subject to revalidation rules for destructive steps.

Implementation is planned through [Phase 1 seams and Phase 2 migration gates](../04-development/development-plan.md#technology-transition). Acceptance of this direction does not mark any service, migration, or parity task complete.
