# Application tracing

Add `"telemetry": {"tracing": {"enabled": true}}` to a `v1alpha2` service or
scheduled component. The platform injects the Pod-local OTLP/HTTP protobuf endpoint
`http://127.0.0.1:4318`, stable service name and parent-based sampler settings.
A platform-managed forwarder reads a rotating ten-minute Pod-bound token for
`platform-telemetry` on each batch and authenticates to the private gateway.
Only the forwarder mounts the token; the application exports to localhost using
ordinary SDK configuration and needs no token-file hook or static bearer header.

For a public service, the platform access boundary creates a new W3C trace
context after discarding client `traceparent`, `tracestate`, and `baggage`. It
forwards `traceparent` only after admission. Instrumented services should
continue that parent decision; a scheduled job starts an independent trace
using the injected root sampling probability. Calls to in-project services
should propagate only `traceparent`. Trace context grants no access.

- **Spring Boot:** Use [Actuator with OpenTelemetry and OTLP](https://docs.spring.io/spring-boot/reference/actuator/tracing.html), configure HTTP/protobuf export using the injected endpoint, and preserve the W3C parent. Avoid request or response body capture.
- **Quarkus:** Use the [OpenTelemetry tracing extension](https://quarkus.io/guides/opentelemetry-tracing/) with OTLP/HTTP protobuf and the injected endpoint. Keep framework route templates rather than raw URLs.
- **FastAPI:** Use the [OpenTelemetry Python SDK and OTLP exporter](https://opentelemetry.io/docs/languages/python/exporters/) with HTTP/protobuf export to the injected localhost endpoint. Set `ParentBased(TraceIdRatioBased(rate))` and disable automatic exception/message capture when it may contain user content.

The gateway verifies every batch with Kubernetes TokenReview, the current Pod
UID and service account, and a read-only current opt-in catalog view. It drops
application resource claims, span names, links, events, status messages,
unapproved attributes, and raw paths. Only generic span timing, parent IDs,
method, HTTP status, and verified project/component labels are retained. The
operator can query raw traces in Grafana; a project reader can fetch only
`GET /projects/{name}/traces/{trace_id}`, filtered to that project and bounded
to the last 24 hours. An absent trace may have been sampled out or expired.
Exporter failure must not block the application request or job. The forwarder
adds 25m CPU/64 MiB requests and 100m CPU/128 MiB limits per opted-in Pod;
quota and optional aggregate admission include those amounts. Scheduled jobs use
a native restartable init sidecar so the forwarder does not prevent Job completion.
See the [bootstrap and framework reference](../../infrastructure/monitoring/TRACING.md).
