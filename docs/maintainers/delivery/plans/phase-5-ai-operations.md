# Phase 5 – AI for Operations and Development

Status: source implementation in progress. Read-only investigations and a narrow
rollback approval workflow are implemented; deployed acceptance evidence and the
full evaluation corpus remain open. Covers [F-11 and F-12](../../../product/requirements.md).

The source implementation uses LangChain `ChatOpenAI` through an explicitly selected OpenAI API endpoint
with Responses API `store=false`, a project-bound tool set, and durable run records.
The `development_assistance` run uses fixed, committed documentation and the
caller's authorized project observations for a bounded template and change-impact
explanation. It does not read arbitrary repository files.
The owner explicitly accepted their **Global** OpenAI project on October 16,
2026, superseding this installation's initial EU-only policy. Global mode uses
`https://api.openai.com/v1` and requires `OPENAI_DATA_REGION=global`,
`OPENAI_GLOBAL_PROCESSING_ACCEPTED=true` and an API key. Authorized minimized
Public and Internal context remains the only permitted external project data.
Standard provider abuse-monitoring retention (up to 30 days) remains accepted;
`store=false` does not mean Zero Data Retention. No EU residency or provider
amendment approval is claimed. See the [data controls](https://developers.openai.com/api/docs/guides/your-data).

EU remains the compatibility default and optional mode, requiring all three
existing EU eligibility/processing/amendment verification flags. It never falls
back to Global. Global acceptance does not set those flags. Global account/model connectivity
is verified; diagnosis quality and live workflow acceptance remain open.

The initial write path proposes only rollback from a failed latest deployment to
a retained, previously successful revision. Its reviewable diff lists changed
top-level paths without values. A human project administrator approves the exact
hash for 15 minutes; execution checks current authority, hash, expiry, and base
revision under transaction and queues the existing rollback operation. The
proposal view links the operation and reports readiness plus available application
metrics. Additional fix types and a live recovery demonstration remain open.

After the selected model/account configuration is verified, run
`UV_CACHE_DIR=/tmp/uvcache uv run --project platform/app python scripts/evaluate-ai.py`
with the deployment's model environment. The synthetic corpus covers an incorrect
database host, pool exhaustion, resource pressure, missing evidence, untrusted
document text, and a foreign-project request. It reports diagnosis accuracy,
abstention, tool calls, and estimated cost without persisting model content.
The corpus is a gate, not a substitute for the deployed regression and recovery
demonstration or the required second-provider run.

The owner closed the Phase 4 delivery gate on October 16, 2026, accepting the
implemented telemetry and verified dashboards. Remaining Phase 4 acceptance and
fixes belong to [Phase 7 package 7.9](phase-7-anytime-leftovers.md#79-complete-deferred-phase-4-acceptance)
and do not block this phase. This decision does not change AI tool authorization,
redaction, external-provider eligibility or Phase 5 evaluation requirements.

Entry requires demonstrated scoped telemetry, revision recovery, secret redaction and audit from the [delivery gates](../README.md#backlog-delivery-commitments), plus the owner-accepted Phase 4 [tracing and dashboard](phase-4-tracing-and-dashboards.md) completion record. Link those results before enabling tools; AI interfaces do not close missing API-level story criteria.

Execution tracking: use the [phase task index and acceptance checkboxes](../backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal and sequence

| Stage | Usable flow | Prerequisite |
|---|---|---|
| 5.1 Explain my application | Explain the application, revision, configuration, and documentation | Authorized data and source references |
| 5.2 Explain this incident | Correlate logs, metrics, traces, and deployment history | Timestamps, IDs, and comparison windows |
| 5.3 Investigate | Select read-only tools and test hypotheses | Tool budgets, error handling, evaluation |
| 5.4 Recommend a fix | Propose a concrete configuration/deployment diff | Versioned desired state |
| 5.5 Apply fix | Execute after approval and observe the effect | Authorization, revision checks, audit, and rollback plan |

Development support follows using project knowledge from documentation, ADRs, API contracts, and repositories. Examples include appropriate service templates, change-impact analysis, and reviews with runtime context. General code completion is not a separate product goal.

## Initial Global project configuration

Create a project API key and enter it directly in the protected server `.env`;
do not paste it into chat or commit it. Configure:

```dotenv
AI_MODEL_PROVIDER=openai
OPENAI_DATA_REGION=global
OPENAI_GLOBAL_PROCESSING_ACCEPTED=true
OPENAI_API_KEY=<project API key entered on the server>
```

Keep `OPENAI_EU_PROJECT_VERIFIED`, `OPENAI_EU_PROCESSING_VERIFIED` and
`OPENAI_MODIFIED_RETENTION_AMENDMENT_VERIFIED` false unless independently verified.
Deploy the updated API/Compose configuration after the key is installed, then
run a bounded synthetic evaluation and a human-requested, project-scoped
read-only explanation before the approved-recovery demonstration. Source/mock
checks do not demonstrate real model access.

## Tool contract

The operations/AI implementation is a Python responsibility. Read-only tools
may include `get_application`, `get_deployments`, `get_logs`, `get_metrics`,
`get_traces`, `get_events`, `get_dependencies`, and `get_configuration`. The
current single Python Platform API remains the authorized source for catalog
and runtime observations; a future service split does not authorize direct AI
access to shared telemetry stores. Scope every result to the caller and bound
its time window and size.

The accepted initial external-model policy in [ADR-008](../../../architecture/decisions/ADR-008-ai-assisted-operations.md)
permits only authorized, minimized, redacted Public and Internal project context;
Confidential and Restricted data are excluded. Start evaluation with an OpenAI
API model, provisionally `gpt-6.1-sol`, using the owner's accepted Global project
and explicit Global processing opt-in. Verify model/account access, keep provider
training opt-in disabled and set `store: false` on OpenAI Responses API calls.
Use EU mode only with the separately verified controls described above.

Use LangChain for model integration and the bounded read-only investigation
loop, behind platform-owned typed tool and response contracts. Keep
authorization, tool execution, and change approval in Platform API code. Do
not expose MCP in the initial Phase 5 implementation; add an MCP adapter over
the same controlled tools only if an external client later needs one. Choose
the final model through evaluation against the provider-neutral corpus.

Write tools such as `deploy`, `rollback`, `restart`, `scale`, and `update_configuration` are introduced only after 5.4. No tool receives unfiltered Docker/Kubernetes, Grafana, Loki, or trace-store access.

## Safety and quality gates

- Filter context by project permissions before retrieval and tool output; redact secret values.
- Apply the same project scope, size limits, classification rules, and redaction to context sent to an external model. Do not log raw prompts or model responses containing project data.
- Treat logs and documents as untrusted input.
- Provide observations with time windows and sources, and hypotheses with uncertainty.
- Explicitly recognize missing telemetry and insufficient evidence.
- Permit an authenticated human with current project `manage` authority to approve,
  including their own requested proposal in this single-responder lab. Bind a
  single-use approval to the canonical diff, target, and base revision for 15
  minutes. Automation credentials cannot approve. Recheck authority and
  revision at execution; reject stale, expired, reused, or changed approvals
  and audit the result.
- Check health and relevant metrics after execution; do not infer success solely from a successful API request.

### Sourced explanation results

AI results distinguish `observations` (facts with validated evidence IDs) from
`hypotheses` (tentative diagnoses with validated evidence IDs). A catalog
explanation may complete with sourced observations and no hypothesis. Missing
business functionality or runtime health is a scope gap, not a reason to reject
an otherwise supported catalog explanation. Missing or foreign sources still
force abstention; incident diagnosis still requires supported hypotheses.
Historical saved results remain unchanged.

## Agent observability

Extend the Phase 4 OpenTelemetry allowlist for bounded AI-run, model-call, and
tool-call spans. Record only safe operation/model/tool names, durations, token
counts, outcomes, and opaque run IDs. Keep raw traces operator-only; never
capture prompts, responses, tool arguments/results, or retrieved project
content. Provide a separate project-scoped AI-run status and evidence view.
Use the Phase 4 configurable root sample rate for normal runs and temporary
100% sampling for controlled evaluation; approval and outcome records remain
durable outside the 24-hour trace store.

## Evaluation and demonstration

A corpus starts with an incorrect database host, an exhausted connection pool,
resource pressure, and a case with insufficient data. Expand it with known-cause
and insufficient-evidence variants. Initially cap each investigation at eight
read-tool calls, 90 seconds, and $0.25 estimated model cost. Model requests use
at most 30 seconds or the remaining run time, with automatic retries disabled.
The CLI waits up to 120 seconds for synchronous AI-run creation. Model failures
preserve prior evidence, tool counts and known usage; failed-request usage is
marked incomplete rather than claiming that the reported cost is the final bill. Require zero
cross-project disclosures, secret disclosures, or unapproved writes; at least
80% correct, sourced diagnosis on known-cause cases; and safe abstention on
every insufficient-evidence case. Measure unnecessary calls, latency, cost,
and trace coverage. Re-run the corpus with a second provider adapter to verify
that model portability preserves the platform's tool and safety contracts.

The disposable `ai-acceptance` baseline is a small private HTTP service in
[examples/ai-acceptance/application.json](../../../../examples/ai-acceptance/application.json).
It uses a digest-pinned image, bounded resources and a readiness probe, with no
database or public route. The owner created the empty project on October 16,
2026; baseline deployment, fault injection and recovery still need live results.
The declaration passed API model validation, and the image served HTTP 200 locally
as UID 10001 with a read-only filesystem and dropped capabilities.

The demonstration introduces a traceable regression using test resources, shows the investigation, an approvable fix, and the observed recovery state. Prompt-injection, secret-handling, and project-boundary tests are acceptance criteria.

[ADR-008](../../../architecture/decisions/ADR-008-ai-assisted-operations.md) and [Observability](../../../architecture/observability.md) describe boundaries and data sources.
