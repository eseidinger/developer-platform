# Architecture Decision Records

[Back to documentation overview](../README.md)

An ADR records context, alternatives, a decision, consequences, and validation. ADRs 001–008 were created on **September 25, 2026**; this is not necessarily the date of the original decision. Later ADRs record their creation and decision status individually.

| ADR | Topic | Status |
|---|---|---|
| [001](ADR-001-platform-api-abstraction.md) | Technology-independent API and provider abstraction | Accepted public-contract principle; second provider optional in Phase 5 |
| [002](ADR-002-docker-vs-kubernetes.md) | Docker, hybrid, or Kubernetes | Accepted hybrid topology; no additional workload adapter in current scope |
| [003](ADR-003-postgresql-provisioning.md) | PostgreSQL provisioning and human access | Proposed; database/Secret provisioning inspected in source |
| [004](ADR-004-identity-and-access-management.md) | Generic OIDC with Keycloak reference deployment and platform-owned authorization | Accepted October 2, 2026; source implementation, deployment acceptance pending |
| [005](ADR-005-observability-watchdog.md) | Monitoring and independent watchdog | Proposed; implementation scope established |
| [006](ADR-006-python-quarkus-evolution.md) | Python application and optional polyglot evolution | Current single Python/FastAPI application selected October 4, 2026; polyglot split optional Phase 5 |
| [007](ADR-007-ui-api-deployment.md) | Combined or separate UI/API deployment | Proposed |
| [008](ADR-008-ai-assisted-operations.md) | AI for development and operations | Accepted product focus; execution design proposed |
| [009](ADR-009-edge-and-cluster-ingress.md) | Caddy edge and Traefik cluster ingress | Accepted for hybrid starting profile; operational acceptance open |
| [010](ADR-010-single-environment-lab.md) | Single-environment lab and in-place operational checks | Accepted September 27, 2026 |
| [011](ADR-011-watchdog-monitoring-boundary.md) | Lab watchdog monitoring boundary; accepted silent-failure risk | Accepted September 27, 2026 |
| [012](ADR-012-admin-provisioning-baseline.md) | Synchronous administrator provisioning and privileged control plane | Implemented baseline; record acceptance not recorded |
| [013](ADR-013-database-credential-lifecycle.md) | Deterministic project credentials and retained SQL data | Implemented baseline; record acceptance not recorded |
| [014](ADR-014-catalog-availability-monitoring.md) | Catalog-derived probes and explicit retirement | Implemented design; record/live acceptance open |
| [015](ADR-015-verified-backup-bundles.md) | Encrypted recovery bundles and verified-only retention | Implemented design; record acceptance open; policy/evidence in backlog |
| [016](ADR-016-phase-1a-recovery-scope.md) | Omit isolated recovery exercises from Phase 1A | Accepted October 1, 2026 |
| [017](ADR-017-phase-1a-retention-evidence-scope.md) | Omit long-horizon retention evidence from Phase 1A | Accepted October 1, 2026 |
| [018](ADR-018-revocable-ci-deployment-credentials.md) | Revocable OIDC machine credentials for CI deployment | Requirement and Phase 2B placement accepted October 4, 2026; implementation proposed |

ADRs 012–015 record choices observable in source as of September 27, 2026. **Implemented** describes what the code does; it does not imply owner approval of these new records, acceptance of the future design, or completed operational validation. Alternatives describe tradeoffs, not a reconstructed history of owner decisions.

## Decision process

1. Define the problem, constraints, and affected requirements.
2. Describe realistic alternatives and their operational consequences.
3. Plan a bounded proof consistent with ADR-010 and applicable scope decisions: local fixtures or a controlled check on the existing lab. ADR-016 excludes fresh isolated restoration from Phase 1A.
4. The project owner accepts, rejects, or defers the decision; add the date and evidence.
5. Update architecture, development planning, and operational documentation.

**Proposed** does not imply an approved implementation. **Accepted** applies only to established requirements and clearly identifies their scope. **Open** denotes an unresolved choice. Future statuses include **rejected** and **superseded by ADR-NNN**.

Score, Coolify, Dokploy, Backstage, Crossplane, and Kratix are candidates for a research backlog, not selected dependencies. Before implementing a complete custom schema, conduct a small fit-gap assessment to identify reusable elements. Candidate selection requires a current technical assessment.
