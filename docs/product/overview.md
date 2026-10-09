# Product overview and vision

Status: current product overview and target vision. Last reviewed October 9, 2026.

The Developer Platform allows developers to describe an application and its required resources, then provision it reproducibly. It connects the application lifecycle, standardized platform services, and traceable architectural decisions.

The core promise is: **I describe what my application needs; the platform provisions compute, persistence, configuration, access, and observability.**

## Current features

- Versioned declarations for multi-service applications and scheduled components.
- A REST API and CLI with durable operation status and revision-aware updates.
- Per-project PostgreSQL, configuration, secrets, routing, quotas, health checks,
  diagnostics, rollback, and explicit retirement.
- OIDC identities, project-scoped grants, revocable CI credentials, and redacted
  audit events.
- Kubernetes workload restrictions, connectivity policy, monitoring, encrypted
  backups, and external availability signals.

The browser portal is under active development. The current supported automation
path is the Platform API and CLI.

## Users and value

| User | Value |
|---|---|
| Developer | Deploy a web/API application with PostgreSQL without manual infrastructure configuration |
| Platform engineer / operator | Operate shared infrastructure, inventory resources, and investigate failures |
| Software architect | Evaluate implementation options through reproducible labs |
| Tech lead | Understand project ownership, dependencies, and standards |

The platform also serves as a cohesive reference and portfolio project. Its current architecture deliberately uses one Python/FastAPI application for the Platform API and the existing Kubernetes/k3d workload infrastructure. A Kotlin/Spring catalog, Java/Quarkus control plane, separately deployed Python workers, or a direct Docker workload adapter are optional Phase 5 studies, not current acceptance requirements. Technology variety is not a success criterion.

## Product boundaries

The first usable vertical slice covers a project/environment, a containerized and largely stateless HTTP application, PostgreSQL, secrets, routing, and basic operations. Infrastructure is provisioned once as the platform foundation; a new project creates resources on that foundation, not a new cluster.

Labs comparing JSONB with MongoDB, relational with graph persistence, or pgvector with specialized vector stores remain extensions. They provide decision evidence but are not required MVP services.

AI supports development, delivery, and operations. Its initial value is explaining applications and incidents using platform context. A general-purpose coding assistant or a complete AI hosting offering is outside the initial scope.

## Success

Success is demonstrated through the [vertical slice](use-cases.md) and [verifiable requirements](requirements.md): deploy an application, preserve its data, detect failures, apply a change, and remove resources deliberately. The public contract remains free of Kubernetes-specific client fields. If optional Phase 5 adds a second compute provider, it must use that same contract. Measure time to the first healthy application and recovery time; binding targets remain open.
