# Phase 4 — Tracing and Grafana Dashboards

Status: planned. Platform and application tracing, application metrics collection,
and provisioned dashboards are not implemented. This
phase follows the usable Phase 3 source capabilities and precedes AI operations
in [Phase 5](phase-5-ai-operations.md). It extends existing Prometheus, Loki,
Alloy, and operator-only Grafana. Full PLAN-017 monitoring acceptance remains
in the independent [Phase 7 leftovers](phase-7-anytime-leftovers.md); any
telemetry needed for Phase 4 must be verified within this phase.

Execution tracking: [PLAN-021 through PLAN-024](../backlog.md#additional-phase-tasks).
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

### 4.3 — Collect hosted-application metrics (`PLAN-023`)

1. Define and version an opt-in component metrics declaration using one declared
   HTTP port and a bounded path. Advertise the capability; reject unsupported
   fields before side effects. Existing applications stay valid without a metrics
   declaration. Keep the exact JSON shape out of the current developer reference
   until the API accepts it.
2. Discover only accepted, active service components and scrape them through a
   private, platform-controlled path. Do not expose a public metrics route or
   depend on browser/application access grants. Bound scrape time, response size,
   sample and series cardinality, labels, retention and resource cost. Report
   missing or failed scrapes distinctly from healthy zero values.
3. Provide fixed, project-scoped application metric reads through the Platform
   API and keep raw Prometheus/Grafana access operator-only. Prevent arbitrary
   PromQL, cross-project selectors, untrusted labels, secrets, personal data and
   raw URL paths with identifiers from entering shared series or responses.
4. Provision and validate framework-aware operator dashboard templates for
   Spring Boot, Quarkus and FastAPI against their actual metric names. Document
   the required application instrumentation. Each template has an Application
   selector populated from discovered, opted-in targets, qualified by project;
   a dependent Component selector narrows multi-service applications. Selectors
   default to one application and every panel query uses the selected project,
   application and component labels. Do not offer an unbounded all-applications
   selection. These Grafana selectors are operator conveniences, not project
   authorization; project users continue to use the scoped Platform API.
   Use neutral fixtures to test switching applications and components without
   stale or mixed data, request rate, errors, latency, collection failure,
   target retirement and project isolation. A template with empty panels is not
   acceptance evidence.

**Exit evidence:** each opted-in fixture yields bounded request/error/latency
metrics and a working dashboard; undeclared and foreign targets remain
inaccessible, and failed collection is visible without disrupting deployment.
The capability is a platform contract, independent of the application framework.

### 4.4 — Let hosted applications participate in tracing (`PLAN-024`)

1. Define and version an opt-in tracing declaration for service and scheduled
   components, advertise the capability, and reject unsupported fields before
   side effects. Existing declarations remain valid. Do not publish an example
   JSON field in the current developer reference until the API accepts it.
   Document Spring Boot, Quarkus and FastAPI instrumentation recipes using
   OpenTelemetry and OTLP; the platform supplies the private endpoint and
   stable service identity, while the application emits its own spans.
2. At the public access boundary, start a new trace for untrusted external
   requests; strip inbound baggage and `tracestate`. Propagate the generated
   W3C `traceparent` context through the authenticated gateway into
   the application and between declared in-project services. Continue a sampled
   request across synchronous calls; link independent durable work to its
   initiating trace when one exists, without claiming a continuously live
   parent span.
   Set bounded sampling at the boundary and use parent-based sampling in
   instrumented services; scheduled jobs start their own bounded traces.
   Trace context carries no authorization and never replaces application access
   policy or the trusted principal headers.
3. Provide an internal OTLP receiver reachable only by opted-in workloads.
   Before accepting spans, verify workload identity with an audience-bound
   credential or equivalent mechanism and derive project, application and
   component provenance server-side. Document the chosen identity transport and
   collector placement before deployment; network reachability alone is not
   proof of identity. Reject forged resource attributes, revoked/retired targets,
   and cross-project submissions. Allowlist stored attributes and normalize route
   templates; drop arbitrary application attributes before storage. Bound export
   rate, span size, attribute count, sampling, storage and retention. Collection
   outages must not block requests or deployments.
4. Keep raw traces and trace search operator-only. Add a fixed, bounded Platform
   API read for an authorized project's verified application spans, with no
   caller-supplied query language; omit foreign and platform-internal spans even
   when a trace crosses projects. In operator Grafana, link the selected
   application/component dashboard to sampled traces only when verified project
   labels and time windows match. Distinguish absent sampling from collection
   failure. Never export request/response bodies, SQL text/parameters, tokens,
   personal data, raw identifier-bearing URLs or unrestricted baggage.
5. Exercise Spring Boot, Quarkus and FastAPI neutral fixtures: admitted and
   denied public calls, service-to-service calls, scheduled work, sampling gaps,
   restart/retry, collector outage/recovery, forged context and origin labels,
   cross-project denial and retirement. Verify trace-to-log correlation only
   when a trace ID is explicitly emitted in the existing safe log envelope;
   do not treat an arbitrary `correlationId` as a trace ID. Record exact images,
   revisions, trace coverage, resource cost and retention configuration.

**Exit evidence:** an operator follows a sampled admitted request from the
platform boundary into an opted-in app and its downstream component; an
authorized project reader sees only verified spans from that project. Forged
origins and foreign reads fail, sensitive values never enter stored spans, and
the app continues to work when trace collection fails.

## Phase exit and handoff

All four tasks need source, local, and deployed evidence against the recorded
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
