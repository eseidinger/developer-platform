# Phase 5 – AI for Operations and Development

Status: planned. Product focus is accepted; technical design is proposed. Covers [F-11 and F-12](../../../product/requirements.md).

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

The operations/AI implementation is a Python responsibility. Read-only tools may include `get_application`, `get_deployments`, `get_logs`, `get_metrics`, `get_traces`, `get_events`, `get_dependencies`, and `get_configuration`. The current single Python Platform API remains the authorized source for catalog and runtime observations; a future service split does not authorize direct AI access to shared telemetry stores. Scope every result to the caller and bound its time window and size. The MCP implementation and model selection remain open.

Write tools such as `deploy`, `rollback`, `restart`, `scale`, and `update_configuration` are introduced only after 5.4. No tool receives unfiltered Docker/Kubernetes, Grafana, Loki, or trace-store access.

## Safety and quality gates

- Filter context by project permissions before retrieval and tool output; redact secret values.
- Treat logs and documents as untrusted input.
- Provide observations with time windows and sources, and hypotheses with uncertainty.
- Explicitly recognize missing telemetry and insufficient evidence.
- Bind approval to the exact diff, target, and revision; reject stale approval.
- Check health and relevant metrics after execution; do not infer success solely from a successful API request.

## Evaluation and demonstration

A small incident corpus includes an incorrect database host, an exhausted connection pool, resource pressure, and a case with insufficient data. Evaluate evidence quality, diagnosis, safe abstention, unnecessary tool calls, and investigation time/cost.

The demonstration introduces a traceable regression using test resources, shows the investigation, an approvable fix, and the observed recovery state. Prompt-injection, secret-handling, and project-boundary tests are acceptance criteria.

[ADR-008](../../../architecture/decisions/ADR-008-ai-assisted-operations.md) and [Observability](../../../architecture/observability.md) describe boundaries and data sources.
