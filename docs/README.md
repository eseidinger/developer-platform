# SaaS / Developer Platform Documentation

Reviewed against source on September 27, 2026. This documentation covers the product, target architecture, architectural decisions, development sequence, and operations.

## Getting started

| Area | Key question | Documents |
|---|---|---|
| Product | Who are we building for, and why? | [Vision](01-product/vision.md), [Use cases](01-product/use-cases.md), [Requirements](01-product/requirements.md), [Roadmap](01-product/roadmap.md) |
| Architecture | How should the platform work? | [Overview](02-architecture/overview.md), [Technology roles](02-architecture/technology-roles.md), [Infrastructure](02-architecture/infrastructure.md), [Software architecture](02-architecture/software-architecture.md) |
| Contract and cross-cutting concerns | What do applications declare, and how are they secured and observed? | [ApplicationSpec](02-architecture/application-spec.md), [Security](02-architecture/security.md), [Observability](02-architecture/observability.md), [Diagrams](02-architecture/diagrams/README.md) |
| Decisions | Why this approach, and what are the alternatives? | [ADR index](03-decisions/README.md) |
| Development | What has evolved, and what comes next? | [Development plan](04-development/development-plan.md), [Phase 2A multi-service increment](04-development/phase-2a-multi-service-scheduled-application.md), [Phase 2B CI credentials](04-development/phase-2b-ci-deployment-credentials.md), [Phase 2C platform capabilities](04-development/phase-2c-platform-capabilities.md), [UI implementation plan](04-development/ui-implementation-plan.md), [Optional Phase 5 architecture expansion](04-development/phase-5-optional-architecture-expansion.md), [Delivery backlog](04-development/delivery-backlog.md) |
| Operations | How do we install and test the basic platform, and which operational systems are separate? | [Fresh deployment and basic tests](05-operations/fresh-deployment-and-platform-tests.md), [Deployment](05-operations/deployment.md), [Keycloak bootstrap](05-operations/keycloak-bootstrap.md), [Human access and authorization validation](05-operations/human-access-and-authorization-validation.md), [Monitoring](05-operations/monitoring.md), [Backup and recovery](05-operations/backup-recovery.md), [Runbook](05-operations/runbook.md) |

## Status and evidence

The [delivery backlog](04-development/delivery-backlog.md#evidence-conventions) is the authoritative task and evidence register. It distinguishes source implementation, executed local checks and operational acceptance, with dated revisions and environment limits. Update those task records as work ships; the development plan defines sequencing and ADRs define decisions.

- **Confirmed requirement:** an established project constraint, not implementation evidence.
- **Implemented in source:** a concrete code/configuration path, not proof of deployment.
- **Verified locally:** a recorded check passed within its stated scope.
- **Accepted operationally:** the task's acceptance criteria passed in a recorded environment.
- **Proposed / specification draft:** target behavior or a decision still requiring implementation or acceptance.

Target-contract examples use illustrative domains and names. Current lab defaults and pinned versions come from `.env.example`, Compose modules and deployment scripts; review them before installation. Backup targets and the lab response policy have already been selected in the delivery backlog. Source review does not assess whether dependencies are current or verify a deployed installation.

## Maintenance

Architecture pages distinguish the implemented lab from the intended system. The [September 27 source review](04-development/delivery-backlog.md#documentation-review-september-27-2026) records corrected mismatches and remaining implementation gaps. ADRs record rationale and alternatives; `04-development/` records architectural evolution, evidence and planned work. Operations guides identify executable current procedures and label future or deferred exercises separately.

For an architectural change, update the relevant ADR first, followed by affected specifications, requirements, and phases. Supersede accepted ADRs with new records rather than rewriting past decisions. Record verifiable implementation and acceptance evidence beside delivery-backlog tasks; update the development plan only when sequencing or scope changes.
