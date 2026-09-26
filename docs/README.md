# SaaS / Developer Platform Documentation

As of September 26, 2026. This documentation covers the product, target architecture, architectural decisions, development sequence, and operations.

## Getting started

| Area | Key question | Documents |
|---|---|---|
| Product | Who are we building for, and why? | [Vision](01-product/vision.md), [Use cases](01-product/use-cases.md), [Requirements](01-product/requirements.md), [Roadmap](01-product/roadmap.md) |
| Architecture | How should the platform work? | [Overview](02-architecture/overview.md), [Infrastructure](02-architecture/infrastructure.md), [Software architecture](02-architecture/software-architecture.md) |
| Contract and cross-cutting concerns | What do applications declare, and how are they secured and observed? | [ApplicationSpec](02-architecture/application-spec.md), [Security](02-architecture/security.md), [Observability](02-architecture/observability.md), [Diagrams](02-architecture/diagrams/README.md) |
| Decisions | Why this approach, and what are the alternatives? | [ADR index](03-decisions/README.md) |
| Development | What has evolved, and what comes next? | [Development plan](04-development/development-plan.md) |
| Operations | How do we deploy, monitor, and recover? | [Deployment](05-operations/deployment.md), [Monitoring](05-operations/monitoring.md), [Backup and recovery](05-operations/backup-recovery.md), [Runbook](05-operations/runbook.md) |

## Status and evidence

The [implementation alignment report](04-development/implementation-alignment-report.md) records the September 26, 2026 source assessment at revision `bbd509dd4bf3e3dbcb2094cfdaf92a35ab3100f8`, requirements coverage, local verification results, and remaining acceptance gaps.

- **Confirmed requirement:** an established project constraint. These include a technology-independent API, the hybrid starting topology, and AI support for development and operations.
- **Implemented in source:** an administrator-operated Python API provisions PostgreSQL databases/logins and Kubernetes workloads with generated credentials in Secrets. Compose, bootstrap/Ansible automation, monitoring, backups, and watchdog tooling are present.
- **Verified locally:** Python unit/syntax checks, shell syntax, Compose configuration, PHP freshness/SMTP fixture tests and lint, and watchdog/heartbeat Ansible syntax checks passed as recorded in the report.
- **Unverified operationally:** live installation, application/database acceptance, scoped user isolation, failure recovery, isolated restore, and real notification receipt are not established by these checks. Phase 1 remains incomplete.
- **Proposed:** an architectural approach that has not yet been accepted as a product decision.
- **Specification draft:** details that make the contract consistent and the implementation verifiable. They do not imply an implemented interface or an accepted decision.

Examples use illustrative versions, URLs, and names. Actual software versions, domains, capacity, and operational targets must be selected before installation. This documentation is not a current product or version assessment.

## Maintenance

The target architecture in `02-architecture/` describes the intended system. ADRs record rationale and alternatives; `04-development/` records architectural evolution and planned work. Operational documents describe intended procedures until execution evidence is added.

For an architectural change, update the relevant ADR first, followed by affected specifications, requirements, and phases. Supersede accepted ADRs with new records rather than rewriting past decisions. Record verifiable implementation and acceptance evidence for completed features in the development plan.
