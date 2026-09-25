# Architecture Decision Records

[Back to documentation overview](../README.md)

An ADR records context, alternatives, a decision, consequences, and validation. These initial ADRs were created on **September 25, 2026**; this is not necessarily the date of the original decision.

| ADR | Topic | Status |
|---|---|---|
| [001](ADR-001-platform-api-abstraction.md) | Technology-independent API and provider abstraction | Accepted principle; implementation details proposed |
| [002](ADR-002-docker-vs-kubernetes.md) | Docker, hybrid, or Kubernetes | Accepted hybrid starting topology; expansion sequence proposed |
| [003](ADR-003-postgresql-provisioning.md) | PostgreSQL provisioning and human access | Proposed; some behavior reported as implemented |
| [004](ADR-004-identity-and-access-management.md) | IAM and separate permission domains | Proposed |
| [005](ADR-005-observability-watchdog.md) | Monitoring and independent watchdog | Proposed; implementation scope established |
| [006](ADR-006-python-quarkus-evolution.md) | Python prototype and possible Quarkus evolution | Open |
| [007](ADR-007-ui-api-deployment.md) | Combined or separate UI/API deployment | Proposed |
| [008](ADR-008-ai-assisted-operations.md) | AI for development and operations | Accepted product focus; execution design proposed |

## Decision process

1. Define the problem, constraints, and affected requirements.
2. Describe realistic alternatives and their operational consequences.
3. Plan a small proof: provider contract test, restore, access test, or lab.
4. The project owner accepts, rejects, or defers the decision; add the date and evidence.
5. Update architecture, development planning, and operational documentation.

**Proposed** does not imply an approved implementation. **Accepted** applies only to established requirements and clearly identifies their scope. **Open** denotes an unresolved choice. Future statuses include **rejected** and **superseded by ADR-NNN**.

Score, Coolify, Dokploy, Backstage, Crossplane, and Kratix are candidates for a research backlog, not selected dependencies. Before implementing a complete custom schema, conduct a small fit-gap assessment to identify reusable elements. Candidate selection requires a current technical assessment.
