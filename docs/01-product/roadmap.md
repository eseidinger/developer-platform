# Product Roadmap

Status: planning draft as of October 4, 2026. No calendar deadlines or effort commitments have been confirmed. The sequence follows dependencies and verifiable outcomes.

| Phase | User outcome | Acceptance gate |
|---|---|---|
| [1 – Foundation](../04-development/phase-1-foundation.md) | Deploy and observe an application with PostgreSQL on the hybrid installation | 1A verified recovery/alerts, 1B scoped access/audit/security alerts, and 1C durable lifecycle acceptance |
| 2 – Platform API | First deploy a [multi-service application with a scheduled component](../04-development/phase-2a-multi-service-scheduled-application.md), add [revocable CI deployment credentials](../04-development/phase-2b-ci-deployment-credentials.md), then complete the [current-platform capabilities](../04-development/phase-2c-platform-capabilities.md) | Phase 2A multi-service/cron acceptance; Phase 2B non-interactive deployment, scope and immediate revocation; Phase 2C diagnostics, policy, scaling, recovery, and retirement on the existing architecture |
| [3 – Developer Experience](../04-development/phase-3-developer-experience.md) | Guided self-service, controlled database access, and reusable templates | End-to-end journey with a role-aware interface and server-side access enforcement |
| [4 – AI Operations and Development](../04-development/phase-4-ai-operations.md) | Explain platform context, investigate incidents, and propose reviewable changes | Evidence-based diagnosis, evaluation, and a controlled write path |
| [5 – Optional Architecture Expansion](../04-development/phase-5-optional-architecture-expansion.md) | Add a second compute provider or extract deployable services only for a recorded need | Provider parity and/or migration, behavior parity, rollback, and operational evidence for the activated package |

The [amended delivery gates](../04-development/development-plan.md#backlog-delivery-commitments) order Phase 1 as operational protection, accountable access/security alerts, then durable lifecycle. Phase 2A implements the prioritized multi-service/scheduled-component vertical slice. Phase 2B adds revocable CI deployment credentials. Phase 2C completes diagnostics, policies, recovery, and project retirement on the existing Kubernetes infrastructure and single Python API. Optional Phase 5 contains the former service-split and second-provider work. All 20 [backlog stories](../04-development/delivery-backlog.md) remain traceable.

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C. MVP is not a separate delivery stage.

Phase 1 already includes a minimal API/CLI. Phase 2A evolves it for named and scheduled components, Phase 2B enables non-interactive CI deployment, and Phase 2C completes the broader lifecycle in the same Python API.

The sequence follows the selected hybrid topology. A direct Docker workload adapter remains an optional Phase 5 expansion in [ADR-002](../03-decisions/ADR-002-docker-vs-kubernetes.md).

Additional data-store labs, providers, deployable platform services, and a larger VM topology are optional expansions. The multi-service/cron use case remains Phase 2A; its capacity check and acceptance evidence remain required. Architectural evolution and inspected implementation status are documented separately in the [development plan](../04-development/development-plan.md).
