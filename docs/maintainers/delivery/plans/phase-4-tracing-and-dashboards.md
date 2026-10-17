# Phase 4 — Tracing and Grafana Dashboards

Status: **complete by owner direction, October 16, 2026**, at deployed/source
baseline `4681e56`. The owner accepted the implemented telemetry and verified
operator dashboards and directed all remaining acceptance work into the final,
lowest-priority [Phase 9 leftovers](phase-9-anytime-leftovers.md#99-complete-deferred-phase-4-acceptance).
This closes the Phase 4 delivery gate and PLAN-021 through PLAN-024 under an
explicit acceptance exception; deferred checks remain unverified, not passed.

The phase follows the usable Phase 3 source capabilities and precedes AI operations
in [Phase 5](phase-5-ai-operations.md). It extends existing Prometheus, Loki,
Alloy, and operator-only Grafana. Full PLAN-017 monitoring acceptance remains
in the independent [Phase 9 leftovers](phase-9-anytime-leftovers.md); any
remaining Phase 4 acceptance is now tracked in package 9.9 and does not gate Phase 5.

Execution tracking: [PLAN-021 through PLAN-024](../backlog.md#additional-phase-tasks).
The [backlog](../backlog.md) remains the evidence and task-status register.

## Accepted dashboard checks

On October 16, 2026, the owner confirmed live dashboard verification with VEF
(Quarkus, deployed as `vareng`) and ODIP (Spring Boot). These functional dashboard
checks are **passed** for PLAN-022 and the dashboard portion of PLAN-023, alongside
the recorded automated query and provisioning checks. Do not require a repeat
JVM dashboard acceptance run using disposable applications. FastAPI runtime
coverage, unperformed failure/recovery drills, trace/log links, project-access
and retirement checks, and storage/retention evidence remain separate open items.
These performed checks are passed. The subsequent owner-directed completion
decision below closes the delivery tasks while preserving deferred acceptance.

The owner also confirmed the **PostgreSQL** dashboard and new host storage panels
working after deployment through `b347e92` on October 16, 2026. Their live functional
checks are **passed** for PLAN-022 and do not need repeating.

## Goal and boundaries

Correlate an authorized request, its durable operation, provider calls, and
result with bounded traces, then provide useful, versioned operator dashboards
for the signals the platform actually collects. Keep trace storage and shared
Grafana administrative: project users continue to receive only scoped Platform
API observations. Do not ingest request bodies, SQL statements or parameters,
tokens, passwords, secrets, personal data, or unbounded application-supplied
attributes into spans, labels, links, panels, or screenshots.

The original planning baseline had provisioned Prometheus and Loki data sources
but no trace backend or provisioned dashboards. [ADR-021](../../../architecture/decisions/ADR-021-phase-4-tracing-boundary.md)
selects Tempo 3 single-process/local storage, existing Compose Alloy, a private
authenticated workload OTLP gateway, an operator-configurable root sample rate
defaulting to 10%, 24-hour trace retention, and a hard 4 GiB trace-volume
budget. It also fixes the workload identity, app declaration, and project-read
boundaries. These decisions now have implementation and partial deployed evidence in the
backlog; remaining limit/retention verification belongs to Phase 9 package 9.9.

## Ordered work packages

### 4.1 — Add bounded tracing (`PLAN-021`)

1. Define stable trace/span correlation for API ingress, authorization result,
   queued and resumed operations, worker steps, PostgreSQL and Kubernetes
   provider calls, and outbound HTTP dependencies. Link asynchronous work to
   its initiating request without confusing a durable operation ID with a
   continuously live trace. Propagate a safe trace context to platform-owned
   boundaries; never trust arbitrary client span attributes.
2. Instrument the Python API and operation worker, then deploy private Alloy
   and Tempo paths per ADR-021 with the selected sampling, limits, retention,
   network exposure, health checks, and backup/recovery scope.
   Trace delivery failure must not block deployment or weaken authorization.
   Validate the operator-managed sampling probability, apply it through a
   controlled rollout, and verify that downstream components follow the root
   decision. Keep ingest and storage bounds in force at every supported rate.
3. Expose trace IDs only in scoped diagnostic/audit-safe responses where they
   help an authorized reader; keep raw trace search and the Grafana trace data
   source operator-only until a separately authorized project view exists.
4. Test an allowed and a denied request, successful and failed asynchronous
   operations, interruption/retry, backend unavailability, cross-project
   access, and secret/PII redaction. Exercise 0%, the 10% default, and a
   temporary 100% fixture rate; restore the normal setting. Record trace
   completeness, sampled gaps, resource cost, revisions, and the retention
   policy without claiming elapsed-retention results from configuration alone.

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
4. Provision and validate one shared Application metrics dashboard for Spring
   Boot, Quarkus and FastAPI HTTP conventions, plus a Micrometer JVM dashboard
   for JVM/process metrics. Keep project/application/component selectors and
   reviewed runtime dimensions within existing scrape limits. Document
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

1. Add the ADR-021 opt-in `spec.components[].telemetry.tracing.enabled` field
   for service and scheduled
   components, advertise `applicationTracing`, and reject unsupported use before
   side effects. Existing declarations remain valid. Do not publish this as a
   currently accepted field in the developer reference until the API accepts it.
   Document Spring Boot, Quarkus and FastAPI instrumentation recipes using
   OpenTelemetry and OTLP; the platform supplies the private endpoint and
   stable service identity, while the application emits its own spans.
2. At the public access boundary, start a new trace for untrusted external
   requests; strip inbound baggage and `tracestate`. Propagate the generated
   W3C `traceparent` context through the authenticated gateway into the
   application and between declared in-project services. Continue a sampled
   request across synchronous calls; link independent durable work to its
   initiating trace when one exists, without claiming a continuously live
   parent span.
   Set bounded sampling at the boundary and use parent-based sampling in
   instrumented services; scheduled jobs start their own bounded traces.
   Trace context carries no authorization and never replaces application access
   policy or the trusted principal headers.
3. Provide the private Compose OTLP gateway selected in ADR-021. Give each
   opted-in component a no-RBAC ServiceAccount and an explicitly projected,
   Pod-bound 10-minute `platform-telemetry` token, while retaining disabled
   automatic token mounting. Verify every batch with Kubernetes `TokenReview`,
   match current Pod/catalog opt-in state, and derive project, application and
   component provenance server-side. Reject forged resource attributes,
   revoked/retired targets, and cross-project submissions. Allowlist stored
   attributes and normalize route
   templates; drop arbitrary application attributes before storage. Bound export
   rate, span size, attribute count, sampling, storage and retention. Collection
   outages must not block requests or deployments.
4. Keep raw traces and trace search operator-only. Add the fixed ADR-021
   `GET /projects/{name}/traces/{trace_id}` read, requiring current `view`
   permission and returning at most 200 sanitized spans/64 KiB from the last
   24 hours. Omit foreign and platform-internal spans even when a trace crosses
   projects. In operator Grafana, link the selected
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

**Completion record (October 16, 2026):** The owner directed closure of Phase 4
and transfer of its remaining checks to Phase 9 package 9.9. PLAN-021 through
PLAN-024 are complete for delivery sequencing under this explicit exception.
Existing source/local results and node-01 readback remain evidence; VEF/ODIP,
PostgreSQL and host storage dashboard checks remain owner-accepted passed.

The exception covers the unperformed end-to-end tracing/retry/scheduled flows,
project/forged-origin/redaction checks, 0/10/100% sampling, telemetry failure and
recovery, retirement, FastAPI runtime coverage, restart/reprovisioning, trace/log
links, and retention/storage/resource-cost checks listed in package 9.9. It also
covers any implementation corrections needed when those checks are eventually
run. None is claimed to have passed. The original work packages above preserve
the intended criteria; their outstanding execution now belongs to Phase 9.

Phase 5 AI investigation may consume only the authorized,
redacted Platform API views established here, never an unrestricted Grafana or
trace-store credential. Optional architecture expansion moves to Phase 6 and
does not gate tracing, dashboards, or AI operations.

Foundations: [observability architecture](../../../architecture/observability.md),
[ADR-021 tracing decision](../../../architecture/decisions/ADR-021-phase-4-tracing-boundary.md),
[operator monitoring](../../../operators/monitoring.md), and
[Phase 9 monitoring acceptance](phase-9-anytime-leftovers.md).
