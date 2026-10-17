# ADR-021 – Phase 4 Tracing Boundary and Budget

Created and accepted: October 15, 2026. Status: **Accepted design; source
implementation in progress, deployed acceptance pending**. The project owner
delegated the Phase 4 implementation choices. Acceptance still requires the
source, local, and deployed evidence in the
[Phase 4 plan](../../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md).

## Context

The lab has one host, a Compose monitoring stack outside k3d, project workloads
inside k3d and operator-only Grafana. The source adds a Tempo backend; deployed
readback and limits still require acceptance. Workload pods currently
disable automatic Kubernetes ServiceAccount token mounting and have default-deny
egress. The accepted host reserve is at least 8 GiB RAM, 2 CPUs, and 50 GB disk
unallocated to projects. Tracing must not open shared telemetry storage to
project users or put application-supplied data into indexed labels.

## Decision

### Backend and collection path

Use **Grafana Tempo 3 in single-process mode with local filesystem storage** on
the existing private Compose monitoring network. Pin the chosen compatible
Tempo image by digest when implementing it. Provision a Tempo data source in
operator-only Grafana; publish no Tempo host port, public route, or workload
credential. Use the existing Compose Grafana Alloy as the only writer to Tempo.
The Platform API and worker export OTLP/HTTP to Alloy on the private Compose
network. Alloy applies memory limiting, a strict span/resource attribute
allowlist, batching, and bounded exporter queues before forwarding to Tempo.

Opted-in Kubernetes workloads export OTLP/HTTP to a **dedicated private
telemetry gateway** on the same Compose network. Only the gateway accepts
workload traffic. It authenticates and sanitizes each batch, overwrites all
project/application/component provenance, then forwards to Alloy. No workload
can reach Alloy, Tempo, or Grafana directly. The gateway has a private,
fixed address `TELEMETRY_GATEWAY_IP` (default `172.30.80.13` within the current
`PLATFORM_SUBNET`), checked for conflicts at bootstrap. Only opted-in component
pods receive an explicit
TCP 4318 egress rule to it. Its reachability must be demonstrated with the
current k3d/Docker topology before enabling app tracing.

### Application contract and workload identity

The additive `v1alpha2` field is
`spec.components[].telemetry.tracing.enabled: true` for a service or scheduled
component. Omission or `false` means no trace export. Advertise
`applicationTracing` in environment capabilities; reject `true` when unavailable
before provider side effects. No public exporter URL, bearer token, sampling
policy, backend name, arbitrary resource attributes, or collector credentials
belong in an application declaration. Reserve platform-injected OTLP endpoint,
protocol, service identity, and authentication environment settings against
application configuration overrides. The platform does not install tracing
libraries inside images; application owners instrument their code or runtime.

Each opted-in component uses its own no-RBAC ServiceAccount. Keep
`automountServiceAccountToken: false`; explicitly project only a Pod-bound,
10-minute token with audience `platform-telemetry` into that component. The
gateway uses a dedicated minimal Kubernetes credential for `TokenReview` and
read-only Pod lookup plus a read-only catalog role restricted to the current
opt-in and retirement records. It never receives the provisioner credential.
For every accepted batch it requires a successful review
for that audience, matches the reviewed namespace, ServiceAccount and Pod UID
to a currently managed opted-in component, and rejects deleted/retired Pods.
It derives provenance from those verified records, never from OTLP resource
attributes or client headers. A Kubernetes review or catalog lookup failure
denies ingestion; it never changes application authorization or health.

### Context, sampling, data and storage limits

Start a new trace at the public platform boundary; discard client-supplied
`traceparent`, `tracestate`, and `baggage`. Pass only generated W3C
`traceparent` through the authenticated application gateway and permitted
same-project service calls. Cross-project public requests start a new trace.
Durable operations and scheduled jobs create new spans/traces and use a bounded
link to an initiating trace when one exists. Trace context conveys no access
rights and does not replace `X-Platform-Principal-*` headers.

Use an operator-managed root head-sampling probability, validated in the
inclusive range **0.0–1.0**, with **1.0 (100%)** as the default for normal
requests and scheduled jobs. Set it through deployment configuration and apply
changes with a controlled rollout; it is not an application declaration or a
project-user setting. Downstream components use parent-based sampling so they
follow the sampled flag from the trusted platform boundary. On October 17, 2026,
the owner requested 100% tracing, superseding the original 10% default. Acceptance
fixtures may exercise lower rates and must restore **1.0 (100%)** afterward.
A higher rate does not relax the gateway, Alloy, Tempo, ingest, or storage limits below. Head sampling
cannot guarantee that every failed request is retained.

Cap a stored trace at **256 KiB**, an OTLP request at **256 KiB**,
attribute values at **128 bytes**, and stored attributes at **16 per span**.
Store only verified project, application, component and bounded standard span
fields. Drop unknown span/resource attributes, events, links with arbitrary
attributes, baggage, bodies, SQL text/parameters, tokens, personal data, and
raw URLs. Use route templates only when they are platform-derived and bounded;
otherwise omit paths. The gateway and Alloy both enforce the allowlist.

Retain traces for **24 hours**. Use a dedicated host-mounted trace filesystem
with a **4 GiB hard size limit**, outside the source tree and backup capture.
Alert at **2 GiB** and stop trace ingestion at **3 GiB** until compaction returns
usage below 2 GiB; the hard limit protects the host if admission fails. Create
the bounded mount reproducibly with a loop-backed filesystem on the lab host.
Cap aggregate accepted trace ingress at **16 KiB/s sustained with 128 KiB
burst**, using gateway and Tempo limits, and record dropped-span counters.
Initial memory ceilings are **2 GiB for Tempo**, **256 MiB for the gateway**,
and **512 MiB for Alloy** including its existing log work. Recheck these limits
against measured lab traffic and the host reserve before declaring acceptance.
Telemetry loss, sampling, and overload must never block an application request,
deployment, or authorization decision.

**Capacity policy amendment (October 17, 2026):** The owner selected preservation
of 24-hour retention alongside 100% root sampling. The limits above remain the
implemented baseline until a measured resize is reviewed and rolled out. If
combined application and AI telemetry does not fit, propose a bounded storage
increase with coordinated alert/ingestion thresholds and resource limits;
do not automatically shorten retention or reduce sampling. The
[OpenLIT capacity plan](../../maintainers/delivery/plans/phase-5-ai-operations.md#57-add-openlit-instrumentation-plan-034)
requires representative measurements, protected host reserves and deployed
retention/loss evidence. No new filesystem size is selected by this amendment.


### Reads, recovery and failure behavior

Raw Tempo search and Grafana remain operator-only. Add one fixed Platform API
read: `GET /projects/{name}/traces/{trace_id}`. It requires current project
`view` permission, a valid 128-bit trace ID, a maximum 24-hour lookback, and
returns at most 200 sanitized spans and 64 KiB. Filter each returned span by
verified project provenance; omit platform and foreign-project spans even when
they share a trace ID. Return 404 for no retained project span and 503 for a
trace-backend failure. Do not accept TraceQL, arbitrary selectors, or a raw
Grafana link. A sampled-out or expired trace may have no stored spans; show
collector health separately rather than presenting absence as success.
For an admitted, sampled public request, the platform gateway sets a reserved
`X-Platform-Trace-Id` response header with the generated trace ID after removing
any application-supplied value of that header. A project owner can use this ID
with the scoped read; a denied request exposes no project trace reference.

Tempo trace blocks are disposable lab telemetry: exclude them from the platform
backup bundle, as with historical Prometheus/Loki data. Back up versioned
configuration and dashboard definitions, rebuild the trace store on restore,
and explicitly report the lost trace window. The collector/gateway failure
state must be visible through health and drop counters. No trace availability
or retention SLA follows from this decision.

## Alternatives and consequences

Tempo microservices mode would add Kafka and more services to the single-host
lab. Direct workload export to Tempo or Alloy would leave the receiver without
verified project identity. A shared static token would not distinguish
components or revoke with a Pod. Those options are rejected for Phase 4.

The chosen gateway adds a small infrastructure service and a dedicated
`TokenReview` credential. Every batch incurs authentication and Pod/catalog
verification; do not cache the authorization decision across batches. Trace
storage is deliberately short-lived and may contain gaps.
Any inability to enforce the private network path, workload identity, attribute
allowlist, or disk bound blocks deployed Phase 4 acceptance; it is not silently
relaxed by a dashboard or a successful local fixture.

## Validation

Use neutral Spring Boot, Quarkus, and FastAPI fixtures plus the platform API
worker. Prove sampled platform-to-app and same-project service traces, scheduled
root traces, restart/retry links, fixed project readback, forged headers and
resource-label denial, expired/deleted/foreign tokens, collector outage,
overload, storage-bound behavior, redaction, and recovery. Record image digests,
configuration, accepted/dropped span counts, CPU/RAM/disk cost, and a real
deployed readback. The [Phase 4 plan](../../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md)
owns the full task gates.

References: [Tempo monolithic/local deployment](https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/deploy/locally/linux/),
[Alloy OTLP receiver and authentication](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.receiver.otlp/),
[Kubernetes ServiceAccount TokenReview](https://kubernetes.io/docs/concepts/security/service-accounts/),
and [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).
