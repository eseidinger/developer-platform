# Phase 4 — Tracing and Grafana Dashboards

Status: planned. Tracing and provisioned dashboards are not implemented. This
phase follows the usable Phase 3 source capabilities and precedes AI operations
in [Phase 5](phase-5-ai-operations.md). It extends existing Prometheus, Loki,
Alloy, and operator-only Grafana. Full PLAN-017 monitoring acceptance remains
in the independent [Phase 7 leftovers](phase-7-anytime-leftovers.md); any
telemetry needed for Phase 4 must be verified within this phase.

Execution tracking: [PLAN-021 and PLAN-022](../backlog.md#additional-phase-tasks).
The [backlog](../backlog.md) remains the evidence and task-status register.

## Goal and boundaries

Correlate an authorized request, its durable operation, provider calls, and
result with bounded traces, then provide useful, versioned operator dashboards
for the signals the platform actually collects. Keep trace storage and shared
Grafana administrative: project users continue to receive only scoped Platform
API observations. Do not ingest request bodies, SQL statements or parameters,
tokens, passwords, secrets, personal data, or unbounded application-supplied
attributes into spans, labels, links, panels, or screenshots.

The current baseline has provisioned Prometheus and Loki data sources but no
trace backend or provisioned dashboards. Choose and document the tracing
backend and collector path before installation; OpenTelemetry instrumentation
and an operator-only Grafana-compatible backend (such as Tempo) are the
candidate design, not an already accepted runtime choice. Set a sampling,
storage, and retention budget that fits the single-host lab before enabling
collection.

## Ordered work packages

### 4.1 — Add bounded tracing (`PLAN-021`)

1. Define stable trace/span correlation for API ingress, authorization result,
   queued and resumed operations, worker steps, PostgreSQL and Kubernetes
   provider calls, and outbound HTTP dependencies. Link asynchronous work to
   its initiating request without confusing a durable operation ID with a
   continuously live trace. Propagate a safe trace context to platform-owned
   boundaries; never trust arbitrary client span attributes.
2. Instrument the Python API and operation worker, then deploy a private
   collector and trace store with explicit sampling, limits, retention,
   authentication/network exposure, health checks, and backup/recovery scope.
   Trace delivery failure must not block deployment or weaken authorization.
3. Expose trace IDs only in scoped diagnostic/audit-safe responses where they
   help an authorized reader; keep raw trace search and the Grafana trace data
   source operator-only until a separately authorized project view exists.
4. Test an allowed and a denied request, successful and failed asynchronous
   operations, interruption/retry, backend unavailability, cross-project
   access, and secret/PII redaction. Record trace completeness, sampled gaps,
   resource cost, revisions, and the retention policy without claiming an
   elapsed-retention result from configuration alone.

**Exit evidence:** an operator can follow a sampled, synthetic operation across
the API and worker into its provider outcome, while another project cannot
retrieve it and no sensitive value enters the trace path. The platform still
works safely when collection is unavailable.

### 4.2 — Provision useful Grafana dashboards (`PLAN-022`)

1. Provision dashboard JSON and data-source references from versioned source,
   with repeatable deployment and rollback. Start with three operator views:
   **platform health and delivery** (API, operations, readiness and route
   probes), **workloads and capacity** (component status, CPU/memory, quota and
   database signals actually collected), and **telemetry pipeline and
   security** (scrape/collector/backend health, log ingestion, bounded denial
   and audit-derived metrics). Add trace-to-log or operation links only where
   their IDs and time windows are safely correlated.
2. Make every panel's source, unit, time window and missing-data state clear.
   Avoid high-cardinality or application-controlled labels and unsupported
   claims (for example, a protected-route probe is not backend readiness).
   Keep shared Grafana, Loki and trace data sources operator-only; developer
   views must remain filtered by the Platform API.
3. Against a deployed neutral fixture, verify provisioning after fresh start
   and restart, nonempty known-signal panels, useful no-data/error states,
   an injected application failure, a collector/backend failure, and recovery.
   Test panel queries and links as code and retain redacted screenshots and
   datasource/dashboard revisions. Recheck capacity and retention budgets.

**Exit evidence:** the three dashboards are reproducible and help an operator
locate a fixture deployment failure and a telemetry gap without exposing
another project's data or mistaking missing signals for healthy ones.

## Phase exit and handoff

Both tasks need source, local, and deployed evidence against the recorded
installation; neither source JSON nor a green Grafana health check closes the
phase. Record collector/backend images, configuration, dashboard revisions,
sampled trace coverage, resource cost, access denials, and remaining limits in
the backlog. Phase 5 AI investigation may consume only the authorized,
redacted Platform API views established here, never an unrestricted Grafana or
trace-store credential. Optional architecture expansion moves to Phase 6 and
does not gate tracing, dashboards, or AI operations.

Foundations: [observability architecture](../../../architecture/observability.md),
[operator monitoring](../../../operators/monitoring.md), and
[Phase 7 monitoring acceptance](phase-7-anytime-leftovers.md).
