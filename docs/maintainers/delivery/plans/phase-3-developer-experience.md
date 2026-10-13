# Phase 3 – Developer Experience and Access

Status: planned. Covers [F-09, F-10, and N-03](../../../product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](../backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Offer the Python Platform API lifecycle as understandable self-service. The portal
uses the React stack selected in
[ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md); delivery follows the
[UI implementation plan](ui.md). CLI delivery follows the
[CLI implementation plan](cli.md).

The [energy-system use-case enablement plan](energy-system-integration.md) is the
first Phase 3 delivery slice. It delivers generic application identity, component
monitoring, authenticated routing, durability, and recovery capabilities, then
uses separately owned energy-system evidence to verify the use case. Complete
those gates before starting new Phase 3 breadth beyond work already in progress.
Existing portal and CLI work may continue only where it directly enables or
verifies that slice.

## Priority sequence

**Portal increment (October 13, 2026): PLAN-020.** The project
**Application access** UI is implemented in source for governance, groups, policy
definition/activation, human requests/memberships, and consumer/provider service
approval. The owner accepted it for lab sequencing without deployed journey
checks; those outcomes remain unverified. Follow
[UI increment 4a](ui.md#4a-deliver-hosted-application-access-plan-020)
and the [user workflow](../../../developers/ui.md#define-and-approve-application-access).
This is a direct enablement of the priority slice. It does not certify the outstanding identity,
monitoring, integration, and recovery acceptance in the sequence below.

1. Freeze the generic deployment, identity, connectivity, persistence/TLS,
   limits, retention, and application/platform ownership contracts (`PLAN-016`).
2. Deliver hosted-application OIDC and application/platform permission separation
   (`PLAN-009`).
3. Correct component-aware monitoring and define safe cross-application correlation
   (`PLAN-017`).
4. Pass the platform's neutral-fixture authenticated-route and denial gate and
   record the separately owned energy-system suite result (`PLAN-018`).
5. Pass restart and application-level backup/restore reproduction (`PLAN-019`).
6. Resume the broader portal/template journey and human database access
   (`PLAN-006` through `PLAN-008`).

## Work packages

- Provide a portal that uses the Platform API for application metadata, ownership, deployments, redacted configuration, logs, and operations; do not reproduce server-side authorization rules in the UI.
- Provide a CLI over the same versioned public contracts, with understandable errors
  and progress, following the [CLI implementation plan](cli.md).
- Create a web-application/PostgreSQL template, preferably as one deployable artifact.
- Extend the accepted ADR-004 boundary with platform-managed application groups
  and access policies using `browser-session` and `bearer-token` modes. Derive
  hosted-application OIDC clients, browser callback URIs, machine audiences, and
  client-scoped group claims from stable platform resources. Humans use
  first-login approval and machines use pre-authorization; platform roles never
  imply application-group membership. F-10 remains a Phase 3 requirement;
  deferring it requires an explicit scope amendment.
- Offer human database access with a separate identity, authorization, and a controlled tunnel.
- Make ownership, roles, and the distinction between application and platform permissions visible.
- Accept deployed PLAN-020 access-definition and approval screens over the hosted-access
  API. Show pending/approved requests separately from effective memberships and
  active policies; platform roles and CI credentials confer no application groups.
- Build the self-service journey on the multi-service and scheduled-component contract accepted in Phase 2A; do not create a portal-only component model.

Entry requires the Phase 1, Phase 2A, Phase 2B, and Phase 2C backlog gates, including usable authorized diagnostics, recovery, retirement, and CI-credential APIs. Portal completion cannot substitute for those API acceptance results.

## Acceptance

The priority use-case enablement slice first satisfies the exit criteria in the
[energy-system use-case enablement plan](energy-system-integration.md). This
establishes generic hosted-application identity and a real multi-project
consumer/producer journey before the general self-service demonstration. The
concrete energy-system declarations and business assertions remain outside the
platform repository.

A developer creates a sample application, deploys it, and locates an intentionally introduced failure using operation status, health, and logs. Disallowed actions remain blocked server-side even when UI checks are bypassed.

A database user uses credentials distinct from the application. Revoking a grant prevents new access; existing sessions terminate according to the defined session policy. An application OIDC client does not create platform administrator permissions.

## Outcome

A reproducible demo flow with a template, documented role matrix, and UI/API compatibility checks. Demonstrate usability through the complete journey, not screenshots alone.

Foundations: [Use cases](../../../product/use-cases.md),
[Security](../history/security-design.md),
[ADR-007](../../../architecture/decisions/ADR-007-ui-api-deployment.md), and
[ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md).
