# Phase 4 – AI for Operations and Development

Status: planned. Product focus is accepted; technical design is proposed. Covers [F-11 and F-12](../01-product/requirements.md).

Entry requires demonstrated scoped telemetry, revision recovery, secret redaction and audit from the [delivery gates](development-plan.md#backlog-delivery-commitments). Link their evidence before enabling tools; AI interfaces do not close missing API-level story criteria.

Execution tracking: use the [phase task index and acceptance checkboxes](delivery-backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal and sequence

| Stage | Usable flow | Prerequisite |
|---|---|---|
| 4.1 Explain my application | Explain the application, revision, configuration, and documentation | Authorized data and source references |
| 4.2 Explain this incident | Correlate logs, metrics, and deployment history | Timestamps, IDs, and comparison windows |
| 4.3 Investigate | Select read-only tools and test hypotheses | Tool budgets, error handling, evaluation |
| 4.4 Recommend a fix | Propose a concrete configuration/deployment diff | Versioned desired state |
| 4.5 Apply fix | Execute after approval and observe the effect | Authorization, revision checks, audit, and rollback plan |

Development support follows using project knowledge from documentation, ADRs, API contracts, and repositories. Examples include appropriate service templates, change-impact analysis, and reviews with runtime context. General code completion is not a separate product goal.

## Tool contract

The operations/AI implementation is a Python responsibility. Read-only MCP tools include `get_application`, `get_deployments`, `get_logs`, `get_metrics`, `get_events`, `get_dependencies`, and `get_configuration`. Catalog-owned metadata is read through the catalog API; runtime and operational data is read through the Platform API. Both services enforce the caller's scope and limit time windows and result size.

Write tools such as `deploy`, `rollback`, `restart`, `scale`, and `update_configuration` are introduced only after 4.4. No tool receives unfiltered Docker/Kubernetes access. The MCP implementation and model selection remain open.

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

[ADR-008](../03-decisions/ADR-008-ai-assisted-operations.md) and [Observability](../02-architecture/observability.md) describe boundaries and data sources.
