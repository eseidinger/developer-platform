# Application tracing

Add `"telemetry": {"tracing": {"enabled": true}}` to a `v1alpha2` service or
scheduled component. The platform injects an OTLP/HTTP endpoint, stable service
name, parent-based sampler, and `PLATFORM_TELEMETRY_TOKEN_FILE`. It projects a
Pod-bound token for the `platform-telemetry` audience with a ten-minute lifetime.
The application must read that file for **each export batch** and send its
current value as `Authorization: Bearer <token>`. A one-time read or static
`OTEL_EXPORTER_OTLP_HEADERS` setting will stop working after token rotation.
Use an exporter hook or transport that refreshes the header from the file.

For a public service, the platform access boundary creates a new W3C trace
context after discarding client `traceparent`, `tracestate`, and `baggage`. It
forwards `traceparent` only after admission. Instrumented services should
continue that parent decision; a scheduled job starts an independent trace
using the injected root sampling probability. Calls to in-project services
should propagate only `traceparent`. Trace context grants no access.

- **Spring Boot:** Use [Actuator with OpenTelemetry and OTLP](https://docs.spring.io/spring-boot/reference/actuator/tracing.html), configure HTTP/protobuf export with a token-file-aware request interceptor, and preserve the W3C parent. Avoid request or response body capture.
- **Quarkus:** Use the [OpenTelemetry tracing extension](https://quarkus.io/guides/opentelemetry-tracing/) with OTLP/HTTP and a token-file-aware exporter header provider. Keep framework route templates rather than raw URLs.
- **FastAPI:** Use the [OpenTelemetry Python SDK and OTLP exporter](https://opentelemetry.io/docs/languages/python/exporters/) with a custom exporter transport that reloads the token file for every batch. Set `ParentBased(TraceIdRatioBased(rate))` and disable automatic exception/message capture when it may contain user content.

The gateway verifies every batch with Kubernetes TokenReview, the current Pod
UID and service account, and a read-only current opt-in catalog view. It drops
application resource claims, span names, links, events, status messages,
unapproved attributes, and raw paths. Only generic span timing, parent IDs,
method, HTTP status, and verified project/component labels are retained. The
operator can query raw traces in Grafana; a project reader can fetch only
`GET /projects/{name}/traces/{trace_id}`, filtered to that project and bounded
to the last 24 hours. An absent trace may have been sampled out or expired.
Exporter failure must not block the application request or job.
