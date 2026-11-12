# Architecture Decision Records

Status: current decision index; individual records preserve their historical
status and wording.

[Back to documentation overview](../../README.md)

An ADR records context, alternatives, a decision, consequences, and validation.
ADRs 001–008 were created on **September 25, 2026**; this is not necessarily the
date of the original decision. Later ADRs record their creation and decision
status individually.

- **ADR:** [001](ADR-001-platform-api-abstraction.md)
  - **Topic:** Technology-independent API and provider abstraction
  - **Status:** Accepted public-contract principle; second provider optional in
    Phase 6
- **ADR:** [002](ADR-002-docker-vs-kubernetes.md)
  - **Topic:** Docker, hybrid, or Kubernetes
  - **Status:** Accepted hybrid topology; no additional workload adapter in
    current scope
- **ADR:** [003](ADR-003-postgresql-provisioning.md)
  - **Topic:** PostgreSQL provisioning and human access
  - **Status:** Proposed; database/Secret provisioning inspected in source
- **ADR:** [004](ADR-004-identity-and-access-management.md)
  - **Topic:** Generic OIDC with Keycloak reference deployment and
    platform-owned authorization
  - **Status:** Accepted October 2, 2026; source implementation, deployment
    acceptance pending
- **ADR:** [005](ADR-005-observability-watchdog.md)
  - **Topic:** Monitoring and independent watchdog
  - **Status:** Proposed; implementation scope established
- **ADR:** [006](ADR-006-python-quarkus-evolution.md)
  - **Topic:** Python application and optional polyglot evolution
  - **Status:** Current single Python/FastAPI application selected October 4,
    2026; polyglot split optional Phase 6
- **ADR:** [007](ADR-007-ui-api-deployment.md)
  - **Topic:** Combined or separate UI/API deployment
  - **Status:** Proposed
- **ADR:** [008](ADR-008-ai-assisted-operations.md)
  - **Topic:** AI for development and operations
  - **Status:** Accepted product focus; execution design proposed
- **ADR:** [009](ADR-009-edge-and-cluster-ingress.md)
  - **Topic:** Caddy edge and Traefik cluster ingress
  - **Status:** Accepted for hybrid starting profile; operational acceptance
    open
- **ADR:** [010](ADR-010-single-environment-lab.md)
  - **Topic:** Single-environment lab and in-place operational checks
  - **Status:** Accepted September 27, 2026
- **ADR:** [011](ADR-011-watchdog-monitoring-boundary.md)
  - **Topic:** Lab watchdog monitoring boundary; accepted silent-failure risk
  - **Status:** Accepted September 27, 2026
- **ADR:** [012](ADR-012-admin-provisioning-baseline.md)
  - **Topic:** Synchronous administrator provisioning and privileged control
    plane
  - **Status:** Implemented baseline; record acceptance not recorded
- **ADR:** [013](ADR-013-database-credential-lifecycle.md)
  - **Topic:** Deterministic project credentials and retained SQL data
  - **Status:** Implemented baseline; record acceptance not recorded
- **ADR:** [014](ADR-014-catalog-availability-monitoring.md)
  - **Topic:** Catalog-derived probes and explicit retirement
  - **Status:** Implemented design; record/live acceptance open
- **ADR:** [015](ADR-015-verified-backup-bundles.md)
  - **Topic:** Encrypted recovery bundles and verified-only retention
  - **Status:** Implemented design; record acceptance open; policy/evidence in
    backlog
- **ADR:** [016](ADR-016-phase-1a-recovery-scope.md)
  - **Topic:** Omit isolated recovery exercises from Phase 1A
  - **Status:** Accepted October 1, 2026
- **ADR:** [017](ADR-017-phase-1a-retention-evidence-scope.md)
  - **Topic:** Omit long-horizon retention evidence from Phase 1A
  - **Status:** Accepted October 1, 2026
- **ADR:** [018](ADR-018-revocable-ci-deployment-credentials.md)
  - **Topic:** Revocable OIDC machine credentials for CI deployment
  - **Status:** Requirement and Phase 2B placement accepted October 4, 2026;
    implementation proposed
- **ADR:** [019](ADR-019-react-ui-technology-stack.md)
  - **Topic:** React UI technology stack
  - **Status:** Current implementation; future component/styling direction in
    ADR-023
- **ADR:** [020](ADR-020-generic-hosted-application-integration.md)
  - **Topic:** Generic hosted-application integration, group authorization,
    retention, and classification boundary
  - **Status:** Accepted October 11, 2026; implementation and operational
    acceptance open
- **ADR:** [021](ADR-021-phase-4-tracing-boundary.md)
  - **Topic:** Phase 4 trace backend, workload identity, app contract, budget
    and scoped reads
  - **Status:** Accepted October 15, 2026; implementation and operational
    acceptance open
- **ADR:** [022](ADR-022-postgresql-and-s3-storage-scope.md)
  - **Topic:** Retain PostgreSQL with extensions and S3; move other storage
    experiments to a separate lab; add four PostgreSQL extensions afterward
  - **Status:** Accepted November 12, 2026; reduction, extension expansion, and
    migration pending
- **ADR:** [023](ADR-023-mantine-portal-components.md)
  - **Topic:** Migrate portal components and styling to Mantine after PLAN-040
  - **Status:** Accepted November 12, 2026; implementation pending

ADRs 012–015 record choices observable in source as of September 27, 2026.
**Implemented** describes what the code does; it does not imply owner approval
of these new records, acceptance of the future design, or completed operational
validation. Alternatives describe tradeoffs, not a reconstructed history of
owner decisions.

Implementation notes dated October 18 qualify stale present-tense claims in ADRs
003, 012, 013, 019 and 021 without changing their decisions. The table above
preserves each record's original decision/evidence status. Current deployment,
named-store and telemetry behavior belongs in the [architecture](../README.md),
[store guide](../../operators/data-stores.md) and
[UI guide](../../developers/ui.md); pending validation in an old record does not
mean the capability lacks source implementation.

## Decision process

1. Define the problem, constraints, and affected requirements.
1. Describe realistic alternatives and their operational consequences.
1. Plan a bounded proof consistent with ADR-010 and applicable scope decisions:
   local fixtures or a controlled check on the existing lab. ADR-016 excludes
   fresh isolated restoration from Phase 1A.
1. The project owner accepts, rejects, or defers the decision; add the date and
   evidence.
1. Update architecture, development planning, and operational documentation.

**Proposed** does not imply an approved implementation. **Accepted** applies
only to established requirements and clearly identifies their scope. **Open**
denotes an unresolved choice. Future statuses include **rejected** and
**superseded by ADR-NNN**.

Score, Coolify, Dokploy, Backstage, Crossplane, and Kratix are candidates for a
research backlog, not selected dependencies. Before implementing a complete
custom schema, conduct a small fit-gap assessment to identify reusable elements.
Candidate selection requires a current technical assessment.
