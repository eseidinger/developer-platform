# Workload telemetry contracts

See the [monitoring directory guide](README.md) for configuration ownership and
related contracts. Run commands from the repository root.

## Workload AI traces

Components with `telemetry.tracing.enabled=true` send OTLP traces through their
Pod-local forwarder and the authenticated telemetry gateway. Scheduled jobs use
a native sidecar with an exec startup probe against its loopback OTLP listener.
The application starts only after that probe succeeds, avoiding lost shutdown
exports from jobs shorter than the forwarder’s cold start. The gateway replaces
resource identity with verified project/application/component and service name
`<project>.<component>`. Trace/span/parent IDs, start/end times, span kind and
status codes remain available; status messages, arbitrary events/links and
payloads are removed.

Python SDK OTLP batches may omit the sampled bit from `Span.flags` and carry
only remote-parent context bits. The gateway accepts those valid encodings;
sampling remains an SDK decision, while Pod authentication, component opt-in,
batch/rate/storage limits, identifier/time validation and payload minimization
remain admission controls.

The gateway, Alloy and project trace-read API preserve these AI diagnostics:

- **Operation:** `gen_ai.operation.name`: chat, text_completion,
  generate_content, embeddings, execute_tool, invoke_agent, create_agent,
  retrieval
- **Provider/model:** `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.response.model`
- **Usage:** Nonnegative integer `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens`; missing usage is not zero
- **Settings:** Integer `gen_ai.request.max_tokens`, finite
  `gen_ai.request.temperature` (0–2), `gen_ai.request.top_p` (0–1)
- **Result:** Up to four known `gen_ai.response.finish_reasons`, normalized to
  lowercase
- **Tool/error:** Identifier-only `gen_ai.tool.name`, `error.type`; exception
  events may supply the type, never messages/stacks
- **Instrumentation:** Bounded scope name/version; searchable
  `platform.instrumentation.name` and recognized
  `platform.ai.framework=langchain4j`

Metadata identifiers must be ASCII identifiers of at most 128 bytes, with no
whitespace or URLs. Instrumentation versions are at most 32 characters. HTTP
method/status remain supported, and no more than 16 span attributes are
retained. These application-reported metadata fields must not contain customer
identifiers or secrets and do not establish identity, billing or authorization.

AI names become `application.ai.<operation>`. Recognized LangChain4j service
wrapper names become `application.ai.service`; arbitrary application
class/method names are removed. Older `gen_ai.system`,
`gen_ai.usage.prompt_tokens` and `gen_ai.usage.completion_tokens` are normalized
to the corresponding fields above. LangChain4j scalar finish reasons are
accepted, including `TOOL_EXECUTION` mapped to `tool_calls`. Instrumentation and
AI metadata survive the scoped trace API as well as operator Tempo reads.

In Grafana Explore with Tempo, use TraceQL such as:

```traceql
{
  resource.service.name = "vareng.web" &&
  span.platform.ai.framework = "langchain4j"
}
{
  resource.service.name = "vareng.web" &&
  span.gen_ai.request.model = "your-model-id"
}
```

Prompts, completions, messages, conversation/user IDs, tool arguments/results,
provider response IDs, exception text and application-reported cost estimates
are not retained. The change applies to new spans; metadata removed from older
traces cannot be recovered. The 24-hour trace retention and existing storage,
sampling and ingress budgets remain unchanged. Validate locally with
`PYTHONPATH=platform/app/src uv run --project platform/app python scripts/verify/observability/verify-ai-trace-pipeline.py`;
its gateway-sanitized workload fixture verifies real Alloy/Tempo model/framework
searches and project-scoped reads without live model calls.

## Central workload logs and correlation

Alloy discovers project pods and reads logs over the TLS-verified Kubernetes API
using a dedicated `workload-log-reader` service account. Its cluster-wide
administrative RBAC allows only pod get/list/watch and pod-log get: no secrets,
exec, or mutations. Target filters exclude system/access namespaces. It uses
neither the provisioner credential nor host pod-filesystem mounts. Bootstrap
creates `.runtime/log-reader.kubeconfig`; like the controller credential its
file is container-readable under the private `.runtime` directory and mounted
only into the trusted collector. Revoke by deleting `workload-log-reader-token`
and rebootstrap. Never share that file or mount it into a workload.

The collector runs as UID `0` (for the existing host Docker-log reader) and GID
`473`, matching the pinned Alloy image's `473:473`, mode `0770` state directory.
Its named volume stays mounted at `/var/lib/alloy`; no ownership migration,
world-writable permissions, extra capabilities or privileged container is
needed. The root filesystem remains read-only with all capabilities dropped and
`no-new-privileges`. Changing the pinned image requires rechecking this group
and the production-volume fixture, not assuming root can bypass permissions.
Alloy has an internal `/-/ready` health check and bootstrap waits up to 120
seconds for it. API/Prometheus readiness alone is not collector readiness; even
a healthy collector does not prove successful ingestion or elapsed log
retention.

Kubernetes operational logs use `job=kubernetes-workloads`, project, default
environment, application, component, namespace, pod and container labels. Newly
deployed/restarted workloads carry platform-derived pod annotations for revision
and operation ID; Alloy moves those to non-indexed structured metadata. Existing
pods need an ordinary reapply/restart to obtain that metadata. Prometheus never
uses operation/correlation IDs as metric labels.

Central workload storage accepts normal Quarkus and Spring JSON logs with string
`message` and `level` fields, alongside the existing operational envelope:

```json
{"event":"request.completed","level":"info","correlationId":"0123456789abcdef0123456789abcdef"}
```

Events are `application`, `request`, or `job` followed by `.started`, `.ready`,
`.completed`, or `.failed`. Levels are debug/info/warning/error. Correlation is
optional/empty or an opaque lowercase UUID/32-hex identifier supplied and
propagated by applications. It is not a domain identifier interpreted by the
platform. Owners must classify it as Internal or explicitly approved
Confidential; do not put customer identifiers or secrets into it. Unknown fields
are discarded; malformed JSON, free text, invalid envelopes and input lines over
4 KB are dropped before storage.

Normal JSON records retain `message` (1–2000 UTF-8 bytes), normalized `level`,
and optional `logger`, `traceId`, `spanId`, and opaque `correlationId`. Quarkus
`loggerName`/`mdc` and Spring `logger_name`/top-level trace identifiers are
supported; `trace_id`/`span_id` aliases are accepted too. WARN/WARNING normalize
to `warning`, SEVERE to `error`; trace/debug/info/warning/error/fatal are
accepted. Invalid optional metadata is discarded. Trace/span IDs must be nonzero
32/16 hex characters and normalize to lowercase. Logger names use at most 128
identifier characters. Kubernetes timestamps and discovered project labels
supply provenance; application fields cannot override them. Records use
`format=application-json-v1` in the body and a fixed
`log_format=application-json-v1` stream label. Messages, logger names, and trace
IDs are never indexed labels. Operational events keep their existing schema.

Known bearer/basic credential and password/token/key patterns in messages
receive best-effort redaction before storage and again at project reads. Unknown
JSON fields, MDC payloads, headers, and stack traces are discarded. Applications
remain responsible for excluding secrets and inappropriate customer data from
messages; pattern redaction cannot recognize arbitrary sensitive text. AI
diagnostics consume operational event counts, never these messages. Plain-text
diagnostics remain available through the kubelet log endpoint with best-effort
redaction.

Loki's persistent volume and compactor enforce the configured 168-hour
retention. Alloy stores file positions in its own persistent volume.
Collection/write outages may lose logs; neither retention nor a volume is a
delivery guarantee. Loki/Grafana remain operator-only, with no tenant access to
shared queries. `GET /projects/{name}/retained-logs` requires the existing
project view permission, fixes the project/namespace selector server-side,
supports bounded time/component/ pod filters, revalidates returned
streams/records, and audits the read. It never accepts LogQL or returns raw
backend diagnostics. Backend failure is unavailable, not an empty-success
result; retention state `configured` is not live acceptance.

Dated deployment observations are recorded in the
[verification history](VERIFICATION-HISTORY.md).
