# Product Roadmap

Status: planning draft as of September 26, 2026. No calendar deadlines or effort commitments have been confirmed. The sequence follows dependencies and verifiable outcomes.

| Phase | User outcome | Acceptance gate |
|---|---|---|
| [1 – Foundation](../04-development/phase-1-foundation.md) | Deploy and observe an application with PostgreSQL on the hybrid installation | 1A verified recovery/alerts, 1B scoped access/audit/security alerts, and 1C durable lifecycle acceptance |
| [2 – Platform API](../04-development/phase-2-platform-api.md) | Complete diagnostics, policy, recovery and retirement; use the same contract for Kubernetes and direct Docker | Retained single-image backlog packages, provider parity, capability rejection and concurrency/failure recovery |
| [3 – Developer Experience](../04-development/phase-3-developer-experience.md) | Guided self-service, controlled database access, and reusable templates | End-to-end journey with a role-aware interface and server-side access enforcement |
| [4 – AI Operations and Development](../04-development/phase-4-ai-operations.md) | Explain platform context, investigate incidents, and propose reviewable changes | Evidence-based diagnosis, evaluation, and a controlled write path |

The [amended delivery gates](../04-development/development-plan.md#backlog-delivery-commitments) order Phase 1 as operational protection, accountable access/security alerts, then durable lifecycle. Phase 2 completes diagnostics, policies, recovery and project retirement before provider acceptance. All 19 [backlog stories](../04-development/delivery-backlog.md) remain traceable; component-specific criteria stay deferred until separately scheduled.

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C. MVP is not a separate delivery stage.

Phase 1 already includes a minimal API/CLI. Phase 2 stabilizes that contract and adds the second provider; it is not the start of API development.

The sequence follows the selected hybrid topology. A Docker-first implementation remains an alternative in [ADR-002](../03-decisions/ADR-002-docker-vs-kubernetes.md).

Additional data-store labs, multi-component applications, providers, and a larger VM topology will be scheduled as needed. They require a concrete use case, capacity, and operational experience. Architectural evolution and inspected implementation status are documented separately in the [development plan](../04-development/development-plan.md).
