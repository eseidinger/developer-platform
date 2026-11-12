# Product Roadmap

Status: current/next/later roadmap updated November 12, 2026. No calendar
deadlines or effort commitments have been confirmed. The sequence follows
dependencies and verifiable outcomes.

**Storage scope update (November 12, 2026):**
[ADR-022](../architecture/decisions/ADR-022-postgresql-and-s3-storage-scope.md)
retains PostgreSQL with extensions and S3-compatible object storage. Other
project data-store providers are to be removed to simplify the platform and
free CPU and RAM for workloads. A separate storage lab is planned for other
options. The linked Phase 7–9 plans record earlier delivery scope;
non-retained provider expansion and comparisons are superseded. Removal and
migration are tracked in
[PLAN-039](../maintainers/delivery/plans/storage-scope-reduction.md). After it
finishes, [PLAN-040](../maintainers/delivery/plans/postgresql-extension-expansion.md)
adds TimescaleDB, PostGIS, pgmq, and pg_duckdb to PostgreSQL.

- **Phase:**
  [1 – Foundation](../maintainers/delivery/history/phase-1-foundation.md)
  - **State:** Accepted with recorded lab limits
  - **User outcome:** Deploy and observe an application with PostgreSQL on the
    hybrid installation
  - **Acceptance gate:** Recovery/alerts, scoped access/audit/security alerts,
    and durable lifecycle acceptance
- **Phase:** 2 – Platform API
  - **State:** Accepted with recorded deferred production-like checks
  - **User outcome:** Deploy a
    [multi-service application with a scheduled component](../maintainers/delivery/history/phase-2a-multi-service-scheduled-application.md),
    use
    [revocable CI deployment credentials](../maintainers/delivery/history/phase-2b-ci-deployment-credentials.md),
    and operate
    [current-platform capabilities](../maintainers/delivery/history/phase-2c-platform-capabilities.md)
  - **Acceptance gate:** Multi-service/cron, non-interactive deployment and
    revocation, diagnostics, policy, recovery, and retirement
- **Phase:**
  [3 – Developer Experience](../maintainers/delivery/history/phase-3-developer-experience.md)
  - **State:** Complete under owner-directed source/local scope; deployed
    journeys in Phase 10
  - **User outcome:** Guided self-service, controlled database access, and
    reusable templates
  - **Acceptance gate:** Source and local checks accepted; deployed role matrix
    and full journey remain in Phase 10
- **Phase:**
  [4 – Tracing and Grafana Dashboards](../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md)
  - **State:** Complete by owner direction (October 16); remaining checks in
    Phase 10.9
  - **User outcome:** Follow platform and opted-in application operations
    through bounded traces, diagnose platform gaps, and observe application
    metrics
  - **Acceptance gate:** Implemented telemetry and owner-verified dashboards
    accepted; deferred tracing, isolation, failure and retention checks remain
    unverified
- **Phase:**
  [5 – AI Operations and Development](../maintainers/delivery/plans/phase-5-ai-operations.md)
  - **State:** In progress; AI portal (5.6) owner-accepted
  - **User outcome:** Explain platform context, investigate incidents, and
    propose reviewable changes
  - **Acceptance gate:** Live explanation, startup diagnosis, approved rollback
    recovery and primary-provider corpus passed; broader security and acceptance
    remain open; OpenLIT instrumentation (5.7) and AI Grafana dashboards (5.8)
    deployed and functionally owner-verified; operational checks remain open
- **Phase:** [6 – Optional Architecture Expansion](../architecture/evolution.md)
  - **State:** Optional; no entry decision
  - **User outcome:** Add a second compute provider or extract deployable
    services only for a recorded need
  - **Acceptance gate:** Provider parity and/or migration, behavior parity,
    rollback, and operational evidence for the activated package
- **Work package:**
  [Storage Scope Reduction](../maintainers/delivery/plans/storage-scope-reduction.md)
  - **State:** Planned under ADR-022; implementation and migration pending
  - **User outcome:** Keep PostgreSQL and S3, free CPU and RAM for workloads,
    and establish a separate storage lab
  - **Acceptance gate:** Safe migration and retirement, retained-store parity,
    removed-provider denial, and measured capacity gain
- **Work package:**
  [PostgreSQL Extension Expansion](../maintainers/delivery/plans/postgresql-extension-expansion.md)
  - **State:** Planned after storage scope reduction
  - **User outcome:** Use TimescaleDB, PostGIS, pgmq, and pg_duckdb as opt-in
    PostgreSQL extensions
  - **Acceptance gate:** Compatible pinned builds, isolation, bounded capacity,
    backup/restore, upgrade, and application readback
- **Work package:**
  [Mantine UI Migration](../maintainers/delivery/plans/mantine-ui-migration.md)
  - **State:** Planned after PostgreSQL extension expansion
  - **User outcome:** Develop and maintain the portal with one Mantine component
    and styling system
  - **Acceptance gate:** Existing portal journeys, accessibility, responsive
    behavior, API boundaries, and production build pass after migration
- **Phase:**
  [7 – Planned Data Stores](../maintainers/delivery/plans/phase-7-planned-data-stores.md)
  - **State:** Scope narrowed by ADR-022; retirement and migration pending
  - **User outcome:** Retain PostgreSQL, its extensions, and S3-compatible object
    storage for workloads
  - **Acceptance gate:** Retained stores keep their lifecycle, access, backup,
    recovery and safe purge safeguards
- **Phase:**
  [8 – Deferred Data Stores](../maintainers/delivery/plans/phase-8-deferred-data-stores.md)
  - **State:** Superseded by ADR-022; prior implementation evidence retained
  - **User outcome:** Move non-retained storage experiments to a separate lab
  - **Acceptance gate:** No new non-retained provider acceptance on this platform
- **Phase:**
  [9 – Data Store Measurement and Comparison](../maintainers/delivery/plans/phase-9-store-measurement-and-comparison.md)
  - **State:** Cross-store comparison scope superseded by ADR-022
  - **User outcome:** Compare other storage options in the planned storage lab
  - **Acceptance gate:** No cross-store comparison gate on this platform
- **Phase:**
  [10 – Anytime Leftovers](../maintainers/delivery/plans/phase-10-anytime-leftovers.md)
  - **State:** Open, unscheduled, lowest priority
  - **User outcome:** Complete remaining generic acceptance and retained-store
    recovery when capacity allows
  - **Acceptance gate:** Outstanding task criteria remain open; store recovery
    does not gate Phases 7–8

The
[amended delivery gates](../maintainers/delivery/README.md#backlog-delivery-commitments)
order Phase 1 as operational protection, accountable access/security alerts,
then durable lifecycle. Phase 2A implements the prioritized
multi-service/scheduled-component vertical slice. Phase 2B adds revocable CI
deployment credentials. Phase 2C completes diagnostics, policies, recovery, and
project retirement on the existing Kubernetes infrastructure and single Python
API. Phase 4 adds tracing and dashboards, Phase 5 adds AI operations, and
optional Phase 6 contains the former service-split and second-provider work. All
20 [backlog stories](../maintainers/delivery/backlog.md) remain traceable.

Current implementation includes the Kubernetes/k3d provider, one Python/FastAPI
API, PostgreSQL provisioning, the CLI and React portal, and bounded telemetry
with operator dashboards. Phase 4 is complete under its recorded exception.
Phase 5 implements project-scoped explanations/investigations, curated
development assistance and human-approved rollback; its portal is
owner-accepted, while PLAN-010–015 remain open for broader criteria. Phase 7
includes source/local evidence for named PostgreSQL resources and opt-in RustFS,
OpenSearch, Qdrant and dedicated Neo4j Community providers; RustFS, Qdrant and
OpenSearch Dashboards browser access has local login, mode/isolation and
expiry/revocation evidence; Neo4j Browser/private Bolt has local full-access,
independent credential-fencing and cold-recovery evidence. All eight store
performance dashboards and native metrics pipelines are implemented in source;
workload instrumentation examples and version-pinned Parquet/DuckDB comparisons
pass locally. The former Phase 9 measurement and domain comparison scope is
superseded by ADR-022. October 18 evidence adds PostgreSQL's scoped
deterministic exit (EV-67), native provider/extension checks (EV-68/69),
synthetic artifact/outbox/search integration (EV-71), and deployed human
console/session checks (EV-72). Seven EV-71/72 resource purges remain awaiting
verified scheduled backup; zero active leases is not evidence of completed
deletion. Deployed restore/rebuild and natural expiry/operator reviews remain
Phase 10 work. CouchDB and HugeGraph have Phase 8 source implementations;
their earlier acceptance plans are superseded. These statuses reflect
inspected source and the recorded
[backlog evidence](../maintainers/delivery/backlog.md).

Phase 1 is the MVP (minimum viable product), comprising all three gates 1A–1C.
MVP is not a separate delivery stage.

The Phase 3
[hosted-application access UI](../maintainers/delivery/plans/ui.md#4a-deliver-hosted-application-access-plan-020)
(PLAN-020) is implemented in source for groups/policies, first-login approvals,
and machine access requests and approvals. The owner accepted this increment for
lab sequencing with deployed journeys unverified; identity, monitoring,
integration, and recovery gates remain open.

Phase 1 already includes a minimal API/CLI. Phase 2A evolves it for named and
scheduled components, Phase 2B enables non-interactive CI deployment, and Phase
2C completes the broader lifecycle in the same Python API.

The sequence follows the selected hybrid topology. A direct Docker workload
adapter remains an optional Phase 6 expansion in
[ADR-002](../architecture/decisions/ADR-002-docker-vs-kubernetes.md).

The [data store roadmap](data-store-roadmap.md) records the earlier Phase 7–9
provider and comparison scope. Under ADR-022, the platform keeps PostgreSQL
with extensions and S3-compatible storage; other storage experiments move to a
planned separate lab. The
[Parquet artifact example](../../examples/analytics-artifacts/README.md)
remains source evidence for S3 manifests and synthetic comparisons. Recovery
work for retained stores remains in Phase 10. Optional Phase 6 is independent.

Phase 5 implements content-free OpenLIT instrumentation and operator Grafana
dashboards for AI operations, token usage/estimated cost and telemetry health.
The owner confirmed deployed instrumentation, tracing and dashboards work on
October 17; a live explanation has correlated trace, token and cost readback.
Configured root sampling reads back as 100%. Trace-filesystem metric access,
collector-failure/recovery, elapsed retention and sustained-capacity checks
remain open; see the
[deployed evidence](../../infrastructure/monitoring/AI.md#deployed-smoke-check-october-17-2026).

Under ADR-022, the platform retains PostgreSQL with extensions and
S3-compatible object storage. Earlier open-ended store selection and combined
service capacity policies are superseded. Measure reclaimed CPU and RAM as
other providers are retired, and preserve capacity for workloads.
