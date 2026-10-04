# Product Roadmap

Status: planning draft as of October 4, 2026. No calendar deadlines or effort commitments have been confirmed. The sequence follows dependencies and verifiable outcomes.

| Phase | User outcome | Acceptance gate |
|---|---|---|
| [1 – Foundation](../04-development/phase-1-foundation.md) | Deploy and observe an application with PostgreSQL on the hybrid installation | 1A verified recovery/alerts, 1B scoped access/audit/security alerts, and 1C durable lifecycle acceptance |
| [2 – Platform API](../04-development/phase-2-platform-api.md) | First deploy a [multi-service application with a scheduled component](../04-development/phase-2a-multi-service-scheduled-application.md), then extract the Kotlin catalog, Quarkus control plane, and Python workers, complete retained workflows, and add direct Docker parity | Phase 2A multi-service/cron acceptance, followed by contract/state migration and rollback, cross-service authorization/traceability, retained packages, provider parity, capability rejection and concurrency/failure recovery |
| [3 – Developer Experience](../04-development/phase-3-developer-experience.md) | Guided self-service, controlled database access, and reusable templates | End-to-end journey with a role-aware interface and server-side access enforcement |
| [4 – AI Operations and Development](../04-development/phase-4-ai-operations.md) | Explain platform context, investigate incidents, and propose reviewable changes | Evidence-based diagnosis, evaluation, and a controlled write path |

The [amended delivery gates](../04-development/development-plan.md#backlog-delivery-commitments) order Phase 1 as operational protection, accountable access/security alerts, then durable lifecycle with migration-safe ownership seams. Phase 2A is next and implements the prioritized multi-service/scheduled-component vertical slice. Phase 2B then completes diagnostics, policies, recovery and project retirement, passes the catalog/control-plane/worker migration gates, and completes provider acceptance. All 19 [backlog stories](../04-development/delivery-backlog.md) remain traceable.

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C. MVP is not a separate delivery stage.

Phase 1 already includes a minimal API/CLI. Phase 2A evolves it for named and scheduled components before Phase 2B stabilizes the broader service contracts and adds the second provider.

The sequence follows the selected hybrid topology. A Docker-first implementation remains an alternative in [ADR-002](../03-decisions/ADR-002-docker-vs-kubernetes.md).

Additional data-store labs, providers, and a larger VM topology will be scheduled as needed. The multi-service/cron use case is now scheduled as Phase 2A; its capacity check and acceptance evidence remain required. Architectural evolution and inspected implementation status are documented separately in the [development plan](../04-development/development-plan.md).
