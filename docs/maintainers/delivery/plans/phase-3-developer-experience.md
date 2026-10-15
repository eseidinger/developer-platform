# Phase 3 – Developer Experience and Access

Status: planned. Covers [F-09, F-10, and N-03](../../../product/requirements.md).

Execution tracking: use the [phase task index and acceptance checkboxes](../backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Offer the Python Platform API lifecycle as understandable self-service. The portal
uses the React stack selected in
[ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md); delivery follows the
[UI implementation plan](ui.md). CLI delivery follows the
[CLI implementation plan](cli.md).

Phase 3 delivers the broader portal, CLI, template, and human database source
capabilities on the accepted Phase 2C foundation. Remaining generic identity,
monitoring, integration, recovery, and deployed self-service acceptance is
tracked in [Phase 7 anytime leftovers](phase-7-anytime-leftovers.md). Phase 7
may be worked on when capacity allows and does not block Phase 3 delivery.
Unverified Phase 7 criteria cannot be claimed complete for their own tasks.

## Priority sequence

**Portal increment (October 13, 2026): PLAN-020.** The project
**Application access** UI is implemented in source for governance, groups, policy
definition/activation, human requests/memberships, and consumer/provider service
approval. The owner accepted it for lab sequencing without deployed journey
checks; those outcomes remain unverified. Follow
[UI increment 4a](ui.md#4a-deliver-hosted-application-access-plan-020)
and the [user workflow](../../../developers/ui.md#define-and-approve-application-access).
This does not certify the outstanding identity, monitoring, integration, and
recovery acceptance in Phase 7.

1. Implement the broader portal/template journey and human database access
   (`PLAN-006` through `PLAN-008`).
2. Record completed Phase 3 source and local checks. Track the remaining
   deployed acceptance in [Phase 7](phase-7-anytime-leftovers.md) as separate,
   lowest-priority work that may be done at any time.

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
  imply application-group membership. F-10 remains an open story outcome; its
  remaining deployed acceptance is in Phase 7.
- Offer human database access with a separate identity, authorization, and a controlled tunnel.
- Make ownership, roles, and the distinction between application and platform permissions visible.
- Provide PLAN-020 access-definition and approval screens over the hosted-access
  API. Show pending/approved requests separately from effective memberships and
  active policies; platform roles and CI credentials confer no application groups.
  The remaining deployed journey acceptance is in Phase 7.
- Build the self-service journey on the multi-service and scheduled-component contract accepted in Phase 2A; do not create a portal-only component model.

Entry requires the Phase 1, Phase 2A, Phase 2B, and Phase 2C backlog gates, including usable authorized diagnostics, recovery, retirement, and CI-credential APIs. Portal completion cannot substitute for those API acceptance results.

## Acceptance ownership

Record Phase 3 source and local evidence in the backlog. The outstanding
deployed identity, monitoring, integration, recovery, portal/CLI/template, and
human-database journeys belong to [Phase 7](phase-7-anytime-leftovers.md).
Concrete energy-system declarations and business assertions remain outside the
platform repository.

## Outcome

A reproducible demo flow with a template, documented role matrix, and UI/API compatibility checks. Demonstrate usability through the complete journey, not screenshots alone.

Foundations: [Use cases](../../../product/use-cases.md),
[Security](../history/security-design.md),
[ADR-007](../../../architecture/decisions/ADR-007-ui-api-deployment.md), and
[ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md).
