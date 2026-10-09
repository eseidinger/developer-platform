# Product Roadmap

Status: current/next/later roadmap as of October 9, 2026. No calendar deadlines or effort commitments have been confirmed. The sequence follows dependencies and verifiable outcomes.

| Phase | State | User outcome | Acceptance gate |
|---|---|---|---|
| [1 – Foundation](../maintainers/delivery/history/phase-1-foundation.md) | Accepted with recorded lab limits | Deploy and observe an application with PostgreSQL on the hybrid installation | Recovery/alerts, scoped access/audit/security alerts, and durable lifecycle acceptance |
| 2 – Platform API | Accepted with recorded deferred production-like checks | Deploy a [multi-service application with a scheduled component](../maintainers/delivery/history/phase-2a-multi-service-scheduled-application.md), use [revocable CI deployment credentials](../maintainers/delivery/history/phase-2b-ci-deployment-credentials.md), and operate [current-platform capabilities](../maintainers/delivery/history/phase-2c-platform-capabilities.md) | Multi-service/cron, non-interactive deployment and revocation, diagnostics, policy, recovery, and retirement |
| [3 – Developer Experience](../maintainers/delivery/plans/phase-3-developer-experience.md) | Next / active planning | Guided self-service, controlled database access, and reusable templates | End-to-end journey with a role-aware interface and server-side access enforcement |
| [4 – AI Operations and Development](../maintainers/delivery/plans/phase-4-ai-operations.md) | Later / planned | Explain platform context, investigate incidents, and propose reviewable changes | Evidence-based diagnosis, evaluation, and a controlled write path |
| [5 – Optional Architecture Expansion](../architecture/evolution.md) | Optional; no entry decision | Add a second compute provider or extract deployable services only for a recorded need | Provider parity and/or migration, behavior parity, rollback, and operational evidence for the activated package |

The [amended delivery gates](../maintainers/delivery/README.md#backlog-delivery-commitments) order Phase 1 as operational protection, accountable access/security alerts, then durable lifecycle. Phase 2A implements the prioritized multi-service/scheduled-component vertical slice. Phase 2B adds revocable CI deployment credentials. Phase 2C completes diagnostics, policies, recovery, and project retirement on the existing Kubernetes infrastructure and single Python API. Optional Phase 5 contains the former service-split and second-provider work. All 20 [backlog stories](../maintainers/delivery/backlog.md) remain traceable.

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C. MVP is not a separate delivery stage.

Phase 1 already includes a minimal API/CLI. Phase 2A evolves it for named and scheduled components, Phase 2B enables non-interactive CI deployment, and Phase 2C completes the broader lifecycle in the same Python API.

The sequence follows the selected hybrid topology. A direct Docker workload adapter remains an optional Phase 5 expansion in [ADR-002](../architecture/decisions/ADR-002-docker-vs-kubernetes.md).

Additional data-store labs, providers, deployable platform services, and a larger VM topology are optional expansions. The multi-service/cron use case remains Phase 2A; its capacity check and acceptance evidence remain required. Architectural evolution and inspected implementation status are documented separately in the [development plan](../maintainers/delivery/README.md).
