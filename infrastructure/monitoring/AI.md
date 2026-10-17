# AI observability signal contract

OpenLIT 1.45.0 wraps the synchronous OpenAI Responses `create` and `parse` calls
used by LangChain. The platform keeps run/tool spans. The narrow integration does
not initialize a second global provider, unrelated instrumentors, a logger/event
exporter or runtime pricing downloads. The supported application path is
non-streaming synchronous `invoke`; async/streaming integration is not claimed.

The OpenLIT wrapper receives `capture_message_content=False`. Its span facade
accepts only reviewed provider/model/operation and integer token attributes, drops
all events/exception descriptions and fixes the span name before recording.
Environment capture/export overrides are not read. SDK diagnostic loggers are
suppressed because their exception messages can contain provider payloads.
Ordinary platform and hosted-application instrumentation remains independent.

`scripts/verify-ai-trace-pipeline.py` exercises the actual platform HTTP middleware
and focused OpenLIT wrapper with synthetic provider responses through disposable
production-pinned Alloy/Tempo containers. The October 17 local fixture reads back
100 of 100 root request traces and exactly ten model spans, including provider
failure, with correct run/tool/model parentage. It verifies rejection of incoming
public trace context/baggage, private attribute/content removal and preservation
of trusted internal unsampled-parent behavior. This is local delivery evidence;
it does not establish deployed sustained capacity or elapsed 24-hour retention.
The [AI observability workflow](../../.github/workflows/ai-observability.yaml)
also verifies the direct metric pipeline and all provisioned AI dashboard queries.

## Metric ownership and limits

Direct OTLP metrics go to private Alloy `/v1/metrics`, then through an explicit
name/attribute filter, bounded OTLP export to the private Prometheus native OTLP receiver. The authenticated workload gateway still accepts traces only.
Only the API creates AI instruments; the model provider/secret never becomes a
metric label. Collector failure does not change run/approval results.

| Prometheus signal | Producer | Meaning |
| --- | --- | --- |
| `platform_ai_operations_total` | Application | Finished run/model/tool attempts by outcome |
| `platform_ai_runs_total` | Application | Completed, abstained, failed run outcomes |
| `platform_ai_duration_seconds_{bucket,sum,count}` | OpenLIT for model; application for run/tool | Seconds; boundaries .01/.05/.1/.25/.5/1/2/5/10/30/60/90 |
| `platform_ai_in_flight` | Application | In-flight operations; absent is not zero |
| `platform_ai_tool_calls_total` | Application | Calls in finished runs |
| `platform_ai_tokens_total` | Application normalized LangChain usage | Input, cached-input subset and output; do not sum all three |
| `platform_ai_usage_observations_total` | Application | Complete vs unknown estimate/usage observations |
| `platform_ai_estimated_cost_usd_total` | Local pricing module | Known estimates only, with pricing version |
| `platform_ai_changes_total` | Application | Successful approval and queued execution; not recovered workload status |
| `platform_ai_spans_exported_total` | Existing batch exporter observer | Global AI span acceptance/failure by operation; not persistence evidence |
| `platform_ai_cardinality_dropped_total` | Source series guard | New attribute sets refused after source cap |
| `platform_ai_heartbeat_timestamp_seconds` | Metric reader | Process collection heartbeat |
| `platform_ai_configured_root_sample_ratio` | Application config | Configured root sampling, not delivered trace coverage |

OpenLIT's token/cost sinks are intentionally disabled: the pinned SDK cannot
represent missing usage and the selected cache/region/pricing provenance policy
in its default totals. Its provider-duration sink is used directly. There is one
producer per signal; no totals are reconstructed from sampled spans.

Dimensions are server-derived project (128 named projects per process, then
`other`), three action kinds (plus `other`), fixed supported provider/model,
reviewed outcomes, ten tool names (plus `other`), three token types, two
completeness states and the committed pricing version. Only relevant dimensions
are attached to each metric. A process-wide cap of 1024 distinct instrument plus
attribute sets bounds memory; excess new sets are dropped and counted. Histogram
buckets multiply exported series. No run, trace or user IDs are labels. The
15-second metric reader has a two-second HTTP timeout and runs outside requests.
Trace batching retains 512 queued spans/128 per batch; Alloy has separate metric
memory limiting and a 32-batch OTLP queue with two consumers and 30-second retry.

## Cost and missing data

`app.ai_pricing` is the single versioned local rate source for durable estimates,
metrics and conservative budget reservations. Initial rates preserve the existing
reviewed model input/output rates and EU multiplier. Cached-input pricing remains
unverified, so cached calls are explicitly unknown until a reviewed rate update.
Cached tokens are a subset of input and would be charged at the cached rate only.
Missing/invalid usage, failed calls and unpriced models are not zero. A run with
incomplete usage has a null total and separately retained known partial estimate,
usage-completeness and pricing-version metadata. Existing historical records are
not recalculated. Running new records have unknown cost. Provider billing remains
authoritative; cumulative metric totals can be lost/reset and are not bills.

The three operator-only dashboards are generated by
`python3 scripts/generate-dashboards.py`; `--check` verifies reproducibility.
Global exporter/queue/storage panels are explicitly independent of project
selection. Empty/stale data requires checking collection; it is not idle usage.
Safe Tempo links contain only a fixed query and bounded time range.

## Verification and rollout

Run the AI backend tests and `scripts/verify-ai-metric-pipeline.py` (Docker).
The former uses the actual LangChain/OpenAI/OpenLIT path with mock HTTP responses,
including finalization and failure; it checks correlation, cardinality-safe
metadata and seeded content exclusion. The latter uses disposable network-isolated
Alloy/Prometheus containers and the production metric pipeline, checks filtering
and translation, and parses every generated AI dashboard query.

These fixtures are not deployed acceptance. Rollout must verify API restart,
trace and direct-metric readback, collector failure/recovery, comparison with
durable run outcomes and measured CPU/memory/storage overhead. Preserve configured
100% root sampling and 24-hour trace retention; neither implies 100% delivery.
The existing trace filesystem remains 4 GiB pending measured capacity review.

Local evidence (October 17, 2026): 74 AI backend tests and three sampling/context
checks passed; UI lint/typecheck, 40 tests and production build passed. A
network-isolated fixture using Alloy 1.19.2 and Prometheus 3.14.0 verified a known
counter value of seven, stripped private labels/resources, rejected an unreviewed
metric and parsed all 20 AI panel queries. Alloy configuration validation passed.
No deployment, real external-model call, elapsed retention or host-capacity
acceptance is claimed by these checks.

### Deployed smoke check — October 17, 2026

On `node-01`, all three provisioned AI dashboards and their 20 PromQL targets
were queried against the running Grafana/Prometheus installation. The direct
metric heartbeat was fresh and configured root sampling read back as 1.0.
The owner-triggered `vareng` explanation
`da177516-9e60-476e-87ec-932e8ab14f5f` completed with one tool call. Tempo trace
`387241728ec4bacad045cb96c6e3694c` contained one run, two model and one tool span,
with the run ID and model/tool parentage verified. AI spans had only reviewed
attribute keys and no events/status messages. Trace usage and direct metric
totals matched: 1,241 input tokens, 206 output tokens, no cached tokens and
$0.004542 estimated cost, also matching the durable run record. Prompts, answers,
native credentials and tool payloads were not printed by the diagnostics.

The check exposed an incorrect metric-queue selector. The dashboard now selects
the pinned Alloy component ID and `data_type="metrics"`; the disposable pipeline
fixture scrapes Alloy and requires that panel to return exactly one metric-signal
series, in addition to the existing filtering and query checks.

Two observed limitations remain explicit. Range `increase()` panels cannot
recover work preceding the first sample of a new counter; this first run's raw
totals were correct while its range increases were zero. Verify subsequent runs
against an already collected baseline; durable records remain authoritative.
The trace-filesystem panel is unavailable because node-exporter reports
`permission denied` for the Tempo mount. This needs a bounded filesystem-metric
access fix; missing storage data is not a healthy free-space reading.
This smoke check does not establish collector-failure/recovery isolation,
elapsed 24-hour retention, sustained capacity or full PLAN-034/035 acceptance.

**Owner confirmation, October 17, 2026:** The owner confirmed that AI
instrumentation, tracing and dashboards work on the deployed installation.
This records the functional journey as owner-verified; the filesystem-metric
access issue and the unexecuted operational checks above remain open. No second
run's token totals or trace counts are inferred from that confirmation.
