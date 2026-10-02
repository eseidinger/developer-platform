# Phase 3 – Developer Experience and Access

Status: planned. Covers [F-09, F-10, and N-03](../01-product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](delivery-backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Offer the catalog and control-plane lifecycle as understandable self-service. Angular is a portal technology candidate; the final selection remains open.

## Work packages

- Provide a portal that uses the catalog for application metadata/ownership and the control plane for deployments, redacted configuration, logs, and operations; do not reproduce either service's authorization rules in the UI.
- Provide a CLI over the same versioned public contracts, with understandable errors and progress.
- Create a web-application/PostgreSQL template, preferably as one deployable artifact.
- Extend the accepted ADR-004 boundary by automating OIDC clients and controlled redirect URIs for hosted applications while preserving the separation between platform and application permissions. F-10 remains a Phase 3 requirement; deferring it requires an explicit scope amendment.
- Offer human database access with a separate identity, authorization, and a controlled tunnel.
- Make ownership, roles, and the distinction between application and platform permissions visible.
- At phase entry, review the deferred multi-component backlog against a concrete use case and measured capacity. Design independent updates, per-component results/configuration/secrets and a versioned migration path before scheduling implementation. Record the scheduling decision or continued deferral and next review trigger in the development plan; avoid hidden schema changes.

Entry requires the Phase 1 and Phase 2 backlog gates, including usable authorized diagnostics, recovery and retirement APIs. Portal completion cannot substitute for those API acceptance results.

## Acceptance

A developer creates a sample application, deploys it, and locates an intentionally introduced failure using operation status, health, and logs. Disallowed actions remain blocked server-side even when UI checks are bypassed.

A database user uses credentials distinct from the application. Revoking a grant prevents new access; existing sessions terminate according to the defined session policy. An application OIDC client does not create platform administrator permissions.

## Outcome

A reproducible demo flow with a template, documented role matrix, and UI/API compatibility checks. Demonstrate usability through the complete journey, not screenshots alone.

Foundations: [Use cases](../01-product/use-cases.md), [Security](../02-architecture/security.md), [ADR-007](../03-decisions/ADR-007-ui-api-deployment.md).
