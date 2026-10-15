# Phase 5 – AI for Operations and Development

Status: planned. Product focus and technical design are accepted; implementation
and acceptance evidence remain open. Covers [F-11 and F-12](../../../product/requirements.md).

Entry requires demonstrated scoped telemetry, revision recovery, secret redaction and audit from the [delivery gates](../README.md#backlog-delivery-commitments), plus the Phase 4 [tracing and dashboard](phase-4-tracing-and-dashboards.md) evidence. Link those results before enabling tools; AI interfaces do not close missing API-level story criteria.

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
API model, provisionally `gpt-6.1-sol`, using an eligible EU-resident API project
and EU regional processing. Verify account, model, endpoint, and tier eligibility
and fail closed if EU processing is unavailable. Do not opt in to provider
training; set `store: false` on OpenAI Responses API calls. The owner accepts
OpenAI's default abuse-monitoring retention for this initial boundary.

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
read-tool calls, 90 seconds, and $0.25 estimated model cost. Require zero
cross-project disclosures, secret disclosures, or unapproved writes; at least
80% correct, sourced diagnosis on known-cause cases; and safe abstention on
every insufficient-evidence case. Measure unnecessary calls, latency, cost,
and trace coverage. Re-run the corpus with a second provider adapter to verify
that model portability preserves the platform's tool and safety contracts.

The demonstration introduces a traceable regression using test resources, shows the investigation, an approvable fix, and the observed recovery state. Prompt-injection, secret-handling, and project-boundary tests are acceptance criteria.

[ADR-008](../../../architecture/decisions/ADR-008-ai-assisted-operations.md) and [Observability](../../../architecture/observability.md) describe boundaries and data sources.
