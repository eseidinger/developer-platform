# Phase 3 – Developer Experience and Access

Status: complete by owner-directed scope decision on October 15, 2026.
The remaining F-09/F-10 and deployed acceptance outcomes stay open in
[Phase 9](../plans/phase-9-anytime-leftovers.md).

Execution tracking: use the [phase task index and acceptance checkboxes](../backlog.md#phase-task-index). Each task has one delivery gate; story completion may require later or deferred tasks.

## Goal

Offer the Python Platform API lifecycle as understandable self-service. The portal
uses the React stack selected in
[ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md); delivery follows the
[UI implementation plan](../plans/ui.md). CLI delivery follows the
[CLI implementation plan](../plans/cli.md).

Phase 3 delivers the broader portal, CLI, template, and human database source
capabilities on the accepted Phase 2C foundation. Remaining generic identity,
monitoring, integration, recovery, and deployed self-service acceptance is
tracked in [Phase 9 anytime leftovers](../plans/phase-9-anytime-leftovers.md). Phase 9
may be worked on when capacity allows and does not block Phase 3 delivery.
Unverified Phase 9 criteria cannot be claimed complete for their own tasks.

## Priority sequence

**Portal increment (October 13, 2026): PLAN-020.** The project
**Application access** UI is implemented in source for governance, groups, policy
definition/activation, human requests/memberships, and consumer/provider service
approval. The owner accepted it for lab sequencing without deployed journey
checks; those outcomes remain unverified. Follow
[UI increment 4a](../plans/ui.md#4a-deliver-hosted-application-access-plan-020)
and the [user workflow](../../../developers/ui.md#define-and-approve-application-access).
This does not certify the outstanding identity, monitoring, integration, and
recovery acceptance in Phase 9.

1. Implement the broader portal/template journey and human database access
   (`PLAN-006` through `PLAN-008`).
2. Record completed Phase 3 source and local checks. Track the remaining
   deployed acceptance in [Phase 9](../plans/phase-9-anytime-leftovers.md) as separate,
   lowest-priority work that may be done at any time.

## Work packages

- Provide a portal that uses the Platform API for application metadata, ownership, deployments, redacted configuration, logs, and operations; do not reproduce server-side authorization rules in the UI.
- Provide a CLI over the same versioned public contracts, with understandable errors
  and progress, following the [CLI implementation plan](../plans/cli.md).
- Create a web-application/PostgreSQL template, preferably as one deployable artifact.
- Extend the accepted ADR-004 boundary with platform-managed application groups
  and access policies using `browser-session` and `bearer-token` modes. Derive
  hosted-application OIDC clients, browser callback URIs, machine audiences, and
  client-scoped group claims from stable platform resources. Humans use
  first-login approval and machines use pre-authorization; platform roles never
  imply application-group membership. F-10 remains an open story outcome; its
  remaining deployed acceptance is in Phase 9.
- Offer human database access with a separate identity, authorization, and a controlled tunnel.
- Make ownership, roles, and the distinction between application and platform permissions visible.
- Provide PLAN-020 access-definition and approval screens over the hosted-access
  API. Show pending/approved requests separately from effective memberships and
  active policies; platform roles and CI credentials confer no application groups.
  The remaining deployed journey acceptance is in Phase 9.
- Build the self-service journey on the multi-service and scheduled-component contract accepted in Phase 2A; do not create a portal-only component model.

Entry requires the Phase 1, Phase 2A, Phase 2B, and Phase 2C backlog gates, including usable authorized diagnostics, recovery, retirement, and CI-credential APIs. Portal completion cannot substitute for those API acceptance results.

## Acceptance ownership

Record Phase 3 source and local evidence in the backlog. The outstanding
deployed identity, monitoring, integration, recovery, portal/CLI/template, and
human-database journeys belong to [Phase 9](../plans/phase-9-anytime-leftovers.md).
Concrete energy-system declarations and business assertions remain outside the
platform repository.

## Outcome

The Phase 3 source milestone delivered the portal, CLI, template, and human
database access implementation with local contract and UI/API checks. A
complete deployed demo journey remains a Phase 9 outcome.

## Completion record — October 15, 2026

The owner directed Phase 3 to be marked complete for its source and local
delivery scope at checkout `f7a8aff`. The [backlog](../backlog.md#additional-phase-tasks)
records the CLI's 87-method public API coverage and local tests, portal source
and UI checks, web/PostgreSQL template source and schema tests, and human
database access source and local checks. EV-47 adds owner-accepted live core
human database results on node-01; its later clean deployment was revision
`9826de70829b47f18b8c8018c9348fc81dcb8c43`.

**Owner-directed exception:** Phase 3 completion does not claim a published and
deployed template journey, full portal/CLI role and denial matrix, injected
failure journey, or completed deployed PLAN-020 access screens. It does not
claim the remaining generic identity, monitoring, integration, recovery, and
external energy-workflow acceptance, or the human database firewall, browser
storage, and independent redaction reviews. These named outcomes remain open
under PLAN-006–PLAN-009, PLAN-016–PLAN-020, and [Phase 9](../plans/phase-9-anytime-leftovers.md).
F-09 and F-10 story completion is not inferred from this phase decision.

Foundations: [Use cases](../../../product/use-cases.md),
[Security](security-design.md),
[ADR-007](../../../architecture/decisions/ADR-007-ui-api-deployment.md), and
[ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md).
