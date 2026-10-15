# Product Roadmap

Status: current/next/later roadmap as of October 15, 2026. No calendar deadlines or effort commitments have been confirmed. The sequence follows dependencies and verifiable outcomes.

| Phase | State | User outcome | Acceptance gate |
|---|---|---|---|
| [1 – Foundation](../maintainers/delivery/history/phase-1-foundation.md) | Accepted with recorded lab limits | Deploy and observe an application with PostgreSQL on the hybrid installation | Recovery/alerts, scoped access/audit/security alerts, and durable lifecycle acceptance |
| 2 – Platform API | Accepted with recorded deferred production-like checks | Deploy a [multi-service application with a scheduled component](../maintainers/delivery/history/phase-2a-multi-service-scheduled-application.md), use [revocable CI deployment credentials](../maintainers/delivery/history/phase-2b-ci-deployment-credentials.md), and operate [current-platform capabilities](../maintainers/delivery/history/phase-2c-platform-capabilities.md) | Multi-service/cron, non-interactive deployment and revocation, diagnostics, policy, recovery, and retirement |
| [3 – Developer Experience](../maintainers/delivery/history/phase-3-developer-experience.md) | Complete under owner-directed source/local scope; deployed journeys in Phase 7 | Guided self-service, controlled database access, and reusable templates | Source and local checks accepted; deployed role matrix and full journey remain in Phase 7 |
| [4 – Tracing and Grafana Dashboards](../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md) | Later / planned | Follow platform operations through bounded traces and diagnose health, capacity and telemetry gaps in operator dashboards | Scoped trace correlation, redaction, failure isolation and deployed dashboard evidence |
| [5 – AI Operations and Development](../maintainers/delivery/plans/phase-5-ai-operations.md) | Later / planned | Explain platform context, investigate incidents, and propose reviewable changes | Evidence-based diagnosis, evaluation, and a controlled write path |
| [6 – Optional Architecture Expansion](../architecture/evolution.md) | Optional; no entry decision | Add a second compute provider or extract deployable services only for a recorded need | Provider parity and/or migration, behavior parity, rollback, and operational evidence for the activated package |
| [7 – Anytime Leftovers](../maintainers/delivery/plans/phase-7-anytime-leftovers.md) | Open, unscheduled, lowest priority | Complete remaining generic acceptance when capacity allows | Outstanding task criteria remain open; this phase does not gate Phases 3–5 |

The [amended delivery gates](../maintainers/delivery/README.md#backlog-delivery-commitments) order Phase 1 as operational protection, accountable access/security alerts, then durable lifecycle. Phase 2A implements the prioritized multi-service/scheduled-component vertical slice. Phase 2B adds revocable CI deployment credentials. Phase 2C completes diagnostics, policies, recovery, and project retirement on the existing Kubernetes infrastructure and single Python API. Phase 4 adds tracing and dashboards, Phase 5 adds AI operations, and optional Phase 6 contains the former service-split and second-provider work. All 20 [backlog stories](../maintainers/delivery/backlog.md) remain traceable.

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C. MVP is not a separate delivery stage.

The Phase 3 [hosted-application access UI](../maintainers/delivery/plans/ui.md#4a-deliver-hosted-application-access-plan-020)
(PLAN-020) is implemented in source for groups/policies, first-login approvals,
and machine access requests and approvals. The owner accepted this increment for
lab sequencing with deployed journeys unverified; identity, monitoring,
integration, and recovery gates remain open.

Phase 1 already includes a minimal API/CLI. Phase 2A evolves it for named and scheduled components, Phase 2B enables non-interactive CI deployment, and Phase 2C completes the broader lifecycle in the same Python API.

The sequence follows the selected hybrid topology. A direct Docker workload adapter remains an optional Phase 6 expansion in [ADR-002](../architecture/decisions/ADR-002-docker-vs-kubernetes.md).

Additional data-store labs, providers, deployable platform services, and a larger VM topology are optional expansions. The multi-service/cron use case remains Phase 2A; its capacity check and acceptance evidence remain required. Architectural evolution and inspected implementation status are documented separately in the [development plan](../maintainers/delivery/README.md).
