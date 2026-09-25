# ADR-008 – AI Support for Development and Operations

Created: September 25, 2026. Status: **Accepted product focus**; tool and approval model proposed.

## Context

AI should support operations and development. The platform has relevant context: applications, deployments, telemetry, configuration, and architecture.

## Decision

Place the AI layer above the Platform API. It explains platform context, correlates incidents, and supports changes. A general-purpose model-hosting service is not a prerequisite for this roadmap.

Proposed implementation: MCP as a controlled tool interface, initially read-only. Then introduce change proposals with diffs and execution through deterministic platform operations after explicit approval.

## Alternatives

A logs-only assistant lacks context. Direct infrastructure access bypasses authorization and domain boundaries. Fully automatic remediation increases the potential impact before evaluation and operational evidence are available.

## Consequences

Tool access, retrieval, and telemetry must respect project boundaries. Minimize and redact sensitive data. Hypotheses require evidence and explicit data gaps. Approval binds the target, revision, action, and validity; changed plans require renewed review.

## Validation

Use an incident corpus with expected causes and explicitly unknown cases. Test cross-project access, secret leakage, prompt injection, and unapproved writes. Measure value through diagnosis quality and safe execution.

Details: [Phase 4](../04-development/phase-4-ai-operations.md), [Security](../02-architecture/security.md).
