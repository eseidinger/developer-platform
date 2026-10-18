# Product Roadmap

Status: current/next/later roadmap as of October 18, 2026. No calendar deadlines or effort commitments have been confirmed. The sequence follows dependencies and verifiable outcomes.

| Phase | State | User outcome | Acceptance gate |
|---|---|---|---|
| [1 – Foundation](../maintainers/delivery/history/phase-1-foundation.md) | Accepted with recorded lab limits | Deploy and observe an application with PostgreSQL on the hybrid installation | Recovery/alerts, scoped access/audit/security alerts, and durable lifecycle acceptance |
| 2 – Platform API | Accepted with recorded deferred production-like checks | Deploy a [multi-service application with a scheduled component](../maintainers/delivery/history/phase-2a-multi-service-scheduled-application.md), use [revocable CI deployment credentials](../maintainers/delivery/history/phase-2b-ci-deployment-credentials.md), and operate [current-platform capabilities](../maintainers/delivery/history/phase-2c-platform-capabilities.md) | Multi-service/cron, non-interactive deployment and revocation, diagnostics, policy, recovery, and retirement |
| [3 – Developer Experience](../maintainers/delivery/history/phase-3-developer-experience.md) | Complete under owner-directed source/local scope; deployed journeys in Phase 10 | Guided self-service, controlled database access, and reusable templates | Source and local checks accepted; deployed role matrix and full journey remain in Phase 10 |
| [4 – Tracing and Grafana Dashboards](../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md) | Complete by owner direction (October 16); remaining checks in Phase 10.9 | Follow platform and opted-in application operations through bounded traces, diagnose platform gaps, and observe application metrics | Implemented telemetry and owner-verified dashboards accepted; deferred tracing, isolation, failure and retention checks remain unverified |
| [5 – AI Operations and Development](../maintainers/delivery/plans/phase-5-ai-operations.md) | In progress; AI portal (5.6) owner-accepted | Explain platform context, investigate incidents, and propose reviewable changes | Live explanation, startup diagnosis, approved rollback recovery and primary-provider corpus passed; broader security and acceptance remain open; OpenLIT instrumentation (5.7) and AI Grafana dashboards (5.8) deployed and functionally owner-verified; operational checks remain open |
| [6 – Optional Architecture Expansion](../architecture/evolution.md) | Optional; no entry decision | Add a second compute provider or extract deployable services only for a recorded need | Provider parity and/or migration, behavior parity, rollback, and operational evidence for the activated package |
| [7 – Planned Data Stores](../maintainers/delivery/plans/phase-7-planned-data-stores.md) | Implementation in progress | Extend the PostgreSQL baseline with DuckDB/Parquet/RustFS S3 and targeted OpenSearch, AGE/Neo4j and pgvector/Qdrant providers | Independent resource lifecycle, explicit bindings, scoped private/browser access, functional integration, backup capture and safe purge |
| [8 – Deferred Data Stores](../maintainers/delivery/plans/phase-8-deferred-data-stores.md) | Deferred / owner-scheduled | Add TimescaleDB, ClickHouse, Valkey or MongoDB/CouchDB when selected | Owner selection and operational acceptance for activated providers |
| [9 – Data Store Measurement and Comparison](../maintainers/delivery/plans/phase-9-store-measurement-and-comparison.md) | Planned, unscheduled | Measure selected stores and compare them on versioned workloads | Eight performance dashboards and reproducible quantitative/domain comparisons; no adoption threshold |
| [10 – Anytime Leftovers](../maintainers/delivery/plans/phase-10-anytime-leftovers.md) | Open, unscheduled, lowest priority | Complete remaining generic acceptance and deployed store recovery when capacity allows | Outstanding task criteria remain open; store recovery does not gate Phases 7–8 |

The [amended delivery gates](../maintainers/delivery/README.md#backlog-delivery-commitments) order Phase 1 as operational protection, accountable access/security alerts, then durable lifecycle. Phase 2A implements the prioritized multi-service/scheduled-component vertical slice. Phase 2B adds revocable CI deployment credentials. Phase 2C completes diagnostics, policies, recovery, and project retirement on the existing Kubernetes infrastructure and single Python API. Phase 4 adds tracing and dashboards, Phase 5 adds AI operations, and optional Phase 6 contains the former service-split and second-provider work. All 20 [backlog stories](../maintainers/delivery/backlog.md) remain traceable.

Current implementation includes the Kubernetes/k3d provider, one Python/FastAPI API, PostgreSQL provisioning, the CLI and React portal, and bounded telemetry with operator dashboards. Phase 4 is complete under its recorded exception. Phase 5 implements project-scoped explanations/investigations, curated development assistance and human-approved rollback; its portal is owner-accepted, while PLAN-010–015 remain open for broader criteria. Phase 7 includes source/local evidence for named PostgreSQL resources and opt-in RustFS, OpenSearch, Qdrant and dedicated Neo4j Community providers; RustFS, Qdrant and OpenSearch Dashboards browser access has local login, mode/isolation and expiry/revocation evidence; Neo4j Browser/private Bolt has local full-access, independent credential-fencing and cold-recovery evidence. All eight store performance dashboards and native metrics pipelines are implemented in source; workload instrumentation examples and version-pinned Parquet/DuckDB comparisons pass locally. Their remaining deployed measurement and domain comparison acceptance is Phase 9 work.
October 18 evidence adds PostgreSQL's scoped deterministic exit (EV-67), native
provider/extension checks (EV-68/69), synthetic artifact/outbox/search integration
(EV-71), and deployed human console/session checks (EV-72). Seven EV-71/72
resource purges remain awaiting verified scheduled backup; zero active leases
is not evidence of completed deletion. Deployed restore/rebuild and natural
expiry/operator reviews remain Phase 10 work. Phase 8 providers remain deferred. These statuses reflect inspected source and the recorded [backlog evidence](../maintainers/delivery/backlog.md).

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C. MVP is not a separate delivery stage.

The Phase 3 [hosted-application access UI](../maintainers/delivery/plans/ui.md#4a-deliver-hosted-application-access-plan-020)
(PLAN-020) is implemented in source for groups/policies, first-login approvals,
and machine access requests and approvals. The owner accepted this increment for
lab sequencing with deployed journeys unverified; identity, monitoring,
integration, and recovery gates remain open.

Phase 1 already includes a minimal API/CLI. Phase 2A evolves it for named and scheduled components, Phase 2B enables non-interactive CI deployment, and Phase 2C completes the broader lifecycle in the same Python API.

The sequence follows the selected hybrid topology. A direct Docker workload adapter remains an optional Phase 6 expansion in [ADR-002](../architecture/decisions/ADR-002-docker-vs-kubernetes.md).

The [data store roadmap](data-store-roadmap.md) is incorporated into Phase 7 for planned stores, Phase 8 for deferred stores, Phase 9 for measurement and comparison, and Phase 10 for deployed restore, rebuild and application reconnection acceptance. PostgreSQL remains the reference. DuckDB is an application analytical engine; the [Parquet artifact example](../../examples/analytics-artifacts/README.md) supplies exact-version S3 manifests, verified local reads and synthetic SQL comparison/recovery fixtures. The platform supplies generic provider lifecycle and backup safeguards while ODIP, VEF, Energy and Bot Social own domain experiments. Phase 10 recovery checks do not gate Phase 7/8 provider acceptance. Phase 10 remains last, anytime and lowest priority; optional Phase 6 is independent.

Phase 5 implements content-free OpenLIT instrumentation and operator Grafana dashboards for AI operations, token usage/estimated cost and telemetry health. The owner confirmed deployed instrumentation, tracing and dashboards work on October 17; a live explanation has correlated trace, token and cost readback. Configured root sampling reads back as 100%. Trace-filesystem metric access, collector-failure/recovery, elapsed retention and sustained-capacity checks remain open; see the [deployed evidence](../../infrastructure/monitoring/AI.md#deployed-smoke-check-october-17-2026).

Data stores may be selected at will. Benchmark success criteria, demonstrated benefit and workload/domain triggers do not gate selection or permanent adoption; the agreed provisioning, isolation, recovery and capacity policies still apply.

Selected data-store services remain running together. Capacity planning covers their combined workload; adding another store must not automatically stop existing services. Review a concrete capacity increase when needed.
