# Delivery status and plans

Status: current delivery index as of October 15, 2026. Future phases are proposals
without confirmed dates.

## Architectural evolution

| Date | Milestone | Significance |
|---|---|---|
| September 19, 2026 | Self-service, capabilities, labs; Kubernetes with an external PostgreSQL service | Product scope and initial infrastructure boundaries |
| September 20, 2026 | Security assessments, monitoring outside the cluster, five-VM option, PHP/MySQL watchdog | Failure boundaries and operational requirements |
| September 21, 2026 | Hybrid topology selected for the existing single host | Revised starting topology; deployment not verified |
| September 21, 2026 | Automatic database secrets identified as existing behavior; separate human access proposed | Implementation baseline and next access-management extension |
| September 21, 2026 | MVP vertical slice defined; Python baseline established and Quarkus considered | Inspect the prototype before any rewrite |
| September 23, 2026 | Identity and role management for platform and hosted applications | Proposed IAM model |
| September 24, 2026 | UI/API deployment options and technology-independent Platform API | Shared contract and provider abstraction |
| September 24, 2026 | AI focus on operations/development; ApplicationSpec defined | Extensions above the same API |
| September 25, 2026 | Structured documentation established | Separate architecture, decisions, and planning |
| October 1, 2026 | Kotlin/Spring catalog, Quarkus control plane, and Python automation roles selected | Target ownership boundaries accepted; staged implementation and migration remain open |
| October 2, 2026 | Generic OIDC boundary accepted with Keycloak as the supported lab reference | Platform-owned project grants and Phase 1B roles selected, implemented, and accepted under the recorded owner-directed alert-delivery exception |
| October 4, 2026 | Multi-service application with a cron-triggered component prioritized | F-13 and UC-07 added; versioned contract, migration, internal discovery, scheduled-run status, and Kubernetes acceptance are the next Phase 2A increment |
| October 4, 2026 | Revocable CI deployment credentials prioritized after multi-service support | F-14, UC-08, and ADR-018 added; scoped OIDC machine credentials and immediate platform revocation form Phase 2B; former Phase 2B work moves to 2C |
| October 4, 2026 | Empty-project and machine-driven platform acceptance added to Phase 2B | F-15 and UC-09 add human-bootstrapped test-runner credentials, temporary role personas, and first deployment by CI after empty-project creation |
| October 4, 2026 | Current runtime architecture retained | Phase 2C remains on the existing Kubernetes infrastructure and single Python/FastAPI application; a Docker compute adapter and polyglot service split are optional future work (now Phase 6) |
| October 6, 2026 | React UI stack selected for the Phase 3 portal | React, TypeScript and Vite with typed OpenAPI access, TanStack Query, React Router, shadcn/Base UI, Tailwind, forms/validation, and browser/component tests replace the open Angular candidate |
| October 10, 2026 | Generic capabilities required by the energy-system use case made the Phase 3 priority slice | Application-owned declarations consume generic hosted-application OIDC, authenticated HTTPS egress, component monitoring, restart, and recovery; the platform contains no ODIP/VEF-specific profiles or behavior |
| October 14, 2026 | Tracing and dashboards inserted before AI operations | Phase 4 adds bounded tracing and provisioned operator Grafana dashboards; AI operations moves to Phase 5 and optional architecture expansion to Phase 6 |
| October 15, 2026 | Phase 4 tracing design selected | [ADR-021](../../architecture/decisions/ADR-021-phase-4-tracing-boundary.md) fixes Tempo/Alloy, authenticated app export, opt-in contract, sampling, storage budget, and scoped trace reads; implementation remains open |
| October 15, 2026 | Remaining acceptance moved to the last, anytime phase | Former Phase 3A work is Phase 7: visible, unscheduled leftovers that do not gate Phases 3–5 or optional 6 |

## Implementation status

The [delivery backlog](backlog.md#evidence-conventions) is the source of truth for task status, implementation findings and acceptance evidence. Its imported September 26 baseline records a partial administrator-operated foundation. Phase 1A is complete under the accepted limitations in ADR-011, ADR-016, and ADR-017; Phase 1B is complete under its recorded owner-directed alert-delivery exception; Phase 1C is complete under the limits recorded in its October 3 gate audit. Phase 2A passed its deployed acceptance suite on October 4 under its recorded owner-accepted deferrals for database-row preservation, backup inventory, and representative capacity measurement. Phase 2B is accepted under its recorded deferrals for expiry, controlled identity-provider outage, and deployed backup coverage. Phase 2C is complete with the protected live-drill evidence and accepted single-lab limits recorded in the backlog. Phase 3 is complete under the owner-directed source/local scope and named deployed-acceptance exception in its [completion record](history/phase-3-developer-experience.md#completion-record-october-15-2026). [Phase 7 anytime leftovers](plans/phase-7-anytime-leftovers.md) collects unfinished contract, identity, monitoring, integration, recovery, portal, template, and human-database acceptance; it is listed last and may be done whenever capacity allows. Concrete energy-system declarations and domain assertions remain externally owned. The current delivery architecture remains the existing Kubernetes provider and one Python/FastAPI API application. Consult task notes and the verification register for revisions, environments and limits.

## Work sequence and gates

**PLAN-020**, the [hosted-application access UI](plans/ui.md#4a-deliver-hosted-application-access-plan-020),
is accepted for lab sequencing under an [owner-directed exception](backlog.md#additional-phase-tasks).
The deployed screens and active policy were observed; the deployed approval,
service-access, denial, and audit journeys were waived and remain unverified.
Identity, monitoring, integration, and recovery acceptance remain open.

```mermaid
flowchart LR
    Baseline["Inspect Existing Prototype"] --> P1["1 Foundation and Vertical Slice"]
    P1 --> P2A["2A Multi-service and Scheduled Component"]
    P2A --> P2B["2B CI Deployment Credentials"]
    P2B --> P2C["2C Platform Capabilities"]
    P2C --> P3["3 Developer Experience"]
    P3 --> P4["4 Tracing and Grafana Dashboards"]
    P4 --> P5["5 AI Operations / Development"]
    P5 -. "optional" .-> P6["6 Architecture Expansion"]
    P2C -. "anytime" .-> P7["7 Anytime Leftovers"]
    P1 --> Evidence["Measurements and Operational Evidence"]
    P2A --> Evidence
    P2B --> Evidence
    P2C --> Evidence
    P3 --> Evidence
    P4 --> Evidence
    P5 --> Evidence
    P6 --> Evidence
    P7 --> Evidence
```

| Phase | Entry condition | Outcome / dependency |
|---|---|---|
| [1](history/phase-1-foundation.md) | Access to actual code and target host | 1A operational protection, 1B accountable access/security alerts, 1C durable lifecycle and minimal API/CLI, with internal ownership seams in the Python application |
| [2A](history/phase-2a-multi-service-scheduled-application.md) | Accepted Phase 1 vertical slice | Versioned multi-service contract; internal discovery; independently observable long-running services and cron-triggered component on Kubernetes; lossless single-component migration |
| [2B](history/phase-2b-ci-deployment-credentials.md) | IAM boundary and accepted Phase 2A gate | Empty-project bootstrap; scoped deployment credentials; human-created test runner and temporary role personas; machine-driven deploy/observe and authorization suite; immediate platform denial and redacted audit evidence |
| [2C](history/phase-2c-platform-capabilities.md) | Accepted Phase 2A and 2B vertical slices | Diagnostics, policy, scaling, connectivity, recovery, and retirement on the current Kubernetes provider and single Python API |
| [3](history/phase-3-developer-experience.md) | Complete October 15, 2026 under owner-directed source/local scope | Portal, CLI, template, and human database source capabilities; deployed journey acceptance remains in Phase 7 |
| [4](plans/phase-4-tracing-and-dashboards.md) | Complete October 16, 2026 by owner direction | Implemented tracing, application/JVM/PostgreSQL metrics and verified operator dashboards; remaining acceptance/fixes deferred to Phase 7 package 7.9 |
| [5](plans/phase-5-ai-operations.md) | Owner-accepted Phase 4 delivery gate; deferred checks in Phase 7 are non-gating | Python-based evidence assistance and controlled actions through the Platform API |
| [6](../../architecture/evolution.md) | Optional owner decision after Phase 5; demonstrated need for another compute provider or service boundary | Optional Docker compute adapter and/or polyglot service extraction, each gated by parity, migration, rollback, and operational evidence |
| [7 anytime leftovers](plans/phase-7-anytime-leftovers.md) | Phase 2C foundation; schedule independently when capacity allows | Finish the remaining PLAN-016/009/017/018/019/006/007/008, deployed PLAN-020 acceptance and deferred PLAN-021–024 follow-ups (7.9) and second AI provider evaluation (7.10) without gating Phases 3–5 or optional 6 |

**Phase 1 is the MVP (minimum viable product)** and includes gates 1A, 1B and 1C. Requirement delivery phases labeled “Phase 1 (MVP)” must meet their acceptance minimum by that phase’s exit; later extensions do not defer it.

Basic access enforcement, audit, secrets, and observability start in Phase 1. Phase 3 extends these capabilities rather than removing them from the MVP.

## Current architecture and optional expansion

The selected delivery architecture through Phase 5 is one Python/FastAPI API application using the existing Kubernetes/k3d workload infrastructure. Logical responsibility boundaries remain useful inside that application, but they do not imply separately deployed catalog, control-plane, or worker services. No additional compute adapter is required for current acceptance.

[ADR-001](../../architecture/decisions/ADR-001-platform-api-abstraction.md), [ADR-002](../../architecture/decisions/ADR-002-docker-vs-kubernetes.md), and [ADR-006](../../architecture/decisions/ADR-006-python-quarkus-evolution.md) retain the former expansion design as an optional Phase 6 direction. If the owner activates that phase, it follows these gates:

| Gate | Phase | Required result |
|---|---|---|
| Logical seams | Existing baseline | Stable IDs, grants, deployment revisions, operations, provider execution, and observed state remain logically separated within the Python codebase. Persisted jobs use a versioned envelope/result model. |
| Need and scope decision | Optional Phase 6 entry | Record the concrete limitation that justifies another provider or deployable service and choose only the required expansion package. |
| Catalog extraction | Optional Phase 6 | If selected, Kotlin/Spring Boot owns migrated application metadata and grants only after reconciliation, authorization, backup/restore, and rollback pass. |
| Control-plane migration | Optional Phase 6 | If selected, Quarkus passes public-contract and behavior parity before traffic moves. |
| Worker separation | Optional Phase 6 | If selected, separately deployed Python workers pass interruption, duplicate-delivery, stale-authorization, timeout, and redaction acceptance. |
| Provider portability | Optional Phase 6 | If selected, Kubernetes and Docker adapters pass the same provider contract and end-to-end lifecycle evidence. |

Use one authoritative writer per data type at every migration step. Prefer backfill, compare, cut over, and retain a bounded rollback path over permanent dual writes. Correlate actor, catalog version, desired revision, operation ID, job ID, and provider resource IDs across services. Extend monitoring and recovery coverage before retiring the corresponding FastAPI path.

## Backlog delivery commitments

The [delivery backlog](backlog.md) preserves all 20 permanent DEV/OPS IDs and their acceptance criteria. Its [phase task index](backlog.md#phase-task-index) assigns independently checkable tasks to one gate each, including provider, developer-experience and AI work. Stories may span gates; task completion and story completion are recorded separately. This plan supersedes the former six-milestone plan. No story is dropped or marked complete by this amendment.

Deliver Phase 1 in order: **1A operational protection → 1B accountable access → 1C durable single-application lifecycle**. Phase 1 is complete under its recorded limits. Phase 2A multi-service and scheduled components, Phase 2B CI deployment credentials, and Phase 2C platform capabilities are accepted under their recorded evidence and limitations. Phase 3 is complete under its recorded source/local scope and deferred deployed-journey exception; Phase 4 is complete by owner direction on October 16, 2026, with implemented telemetry and verified dashboards; its remaining acceptance and resulting fixes are deferred to Phase 7 package 7.9. The Phase 4 gate for Phase 5 AI operations is satisfied. Optional Phase 6 remains unscheduled. [Phase 7](plans/phase-7-anytime-leftovers.md) is the last, lowest-priority plan entry and may be worked on at any time; its unfinished checks remain visible without blocking the earlier phases.

The table assigns delivery responsibility by role; named delivery owners, dates, and capacity remain unassigned. Alert response is assigned to the project owner under the lab response policy. Assign a named owner before starting each new package. Story-level completion and any deferred criteria are recorded in the backlog; a delivered phase does not erase its accepted limitations.

| Story | Requirement mapping | Delivery gate and disposition | Accountable role |
|---|---|---|---|
| DEV-001 | F-02/F-13 | Phase 2A accepted: versioned named-component contract, stable internal discovery, independent updates/status, and a non-overlapping cron-triggered component; capacity, database-row, and backup-inventory checks are deferred | Product / API |
| DEV-002 | F-02, N-02 | 1C configuration CRUD/activation for one component; per-component extension deferred | API |
| DEV-003 | N-03/N-04 | 1C secret CRUD/rotation/adoption; per-component extension deferred | API / security |
| DEV-004 | F-06, N-03 | Phase 2C diagnostics: authorized search/follow and terminated-instance retention; Phase 2A adds basic scheduled-run attribution | Observability |
| DEV-005 | F-06, N-07 | Phase 2C diagnostics: inventory and usage/request/limit/quota comparisons | Observability |
| DEV-006 | F-04/F-06/F-13 | 1C observed rollout/health for one component; Phase 2A per-component and scheduled-run reporting | API |
| DEV-007 | F-04/F-05, N-02 | 1C durable retry; Phase 2C retained-revision recovery and dependency checks | API |
| DEV-008 | F-02/F-08, N-07 | Phase 2C scaling/quota/scheduling acceptance; advanced per-component allocation deferred | API / infrastructure |
| DEV-009 | F-02/F-08, N-03 | Phase 2C public/private transitions, TLS and outbound policy; advanced per-component policy deferred | Networking |
| DEV-010 | F-03, N-03/N-05 | 1C binding/preservation; Phase 2C availability and tracked operator recovery requests | API / operations |
| DEV-011 | F-05/F-13, N-02/N-08 | 1C confirmed application removal with retained data; Phase 2A all-component retirement preview/cleanup | API |
| DEV-012 | F-14/F-15, N-03/N-04/N-08 | Phase 2B: empty-project bootstrap plus scoped deployment and test-automation OIDC identities with expiry, rotation, immediate revocation, and machine-driven acceptance | API / security |
| OPS-001 | N-08 | 1B durable audit, inspection, restricted filtering/export and retention | Security |
| OPS-002 | N-06/N-08 extension | 1B configurable security alerts with evidence and tested delivery | Security / operations |
| OPS-003 | N-07, F-06 | Phase 2C host/shared-service/project capacity views and alerts; representative Phase 2A capacity measurement and 1C baseline | Operations |
| OPS-004 | F-01, N-03/N-08 | 1B individual access, roles, revocation; recheck every new data surface | Security / API |
| OPS-005 | F-08, N-03/N-07 | Phase 2C configurable quotas/policy, impact preview and aggregate admission | Infrastructure |
| OPS-006 | N-05 | 1A scheduled encrypted off-host backups and measured isolated restoration; repeat as state grows | Operations |
| OPS-007 | N-06, F-06 | 1A independent failure signals; Phase 2C current-platform coverage and project impact | Operations |
| OPS-008 | F-01/F-05, N-02/N-08 extension | Phase 2C project retirement after reliable deletion, retention inventory and access revocation | API / operations |

Multi-service support, CI credentials, and the Phase 2C platform capabilities are accepted under their owner-recorded evidence and limitations. Phase 3 source and local delivery is complete under its recorded exception; the remaining deployed generic capabilities and self-service journeys are in Phase 7. The component change uses a successor schema and explicit migration; do not silently transform the existing singular application object or claim acceptance from single-image tests. CI acceptance must use a distinct machine identity rather than a developer token. All three Phase 2 increments stay on the existing Kubernetes infrastructure and in the single Python API application.

Generic hosted-application OIDC has source implementation; its remaining acceptance is in Phase 7. Phase 4 adds tracing and operator dashboards before Phase 5 AI operations. Docker portability and the polyglot service split are optional Phase 6 packages and do not gate those additions. No calendar or effort commitments are implied.

## Lab validation constraint

[ADR-010](../../architecture/decisions/ADR-010-single-environment-lab.md) records the owner’s accepted single-environment lab policy. Continue operational checks on the existing platform and external watchdog with explicit impact and recovery steps. Do not provision additional test environments. [ADR-016](../../architecture/decisions/ADR-016-phase-1a-recovery-scope.md) omits new isolated restore exercises and recurring full-restoration scheduling from Phase 1A; existing evidence remains historical reference material.

[ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md) bounds monitoring at the existing external watchdog. Independent detection of its scheduler/hosting failure is excluded from Phase 1A acceptance, with silent failure explicitly accepted by the owner. This is a scope decision, not a passed test or deferred implementation; other monitoring criteria remain required.

## Open decisions and ownership

| Topic | Next step | Gate |
|---|---|---|
| Operational state and acceptance | Use the inspected source baseline in the [backlog evidence](backlog.md#evidence-conventions); inventory live resources and record acceptance exercises | Phase 1 |
| Hosted-application access UI | Revisit waived deployed PLAN-020 journeys before a production-like portal claim | Owner-accepted for lab sequencing; deployed workflows unverified |
| Multi-service scheduled application | Record EV-38 and retain the deferred capacity, database-row, and backup-inventory checks for a later production-like validation | Phase 2A accepted |
| CI deployment credentials | Retain the deferred expiry, controlled identity-provider outage, and backup-coverage checks for a later production-like validation | Phase 2B accepted |
| Energy-system use-case enablement leftovers | Complete remaining PLAN-016, PLAN-009, PLAN-017, PLAN-018, and PLAN-019 evidence in the [anytime leftovers plan](plans/phase-7-anytime-leftovers.md) when scheduled; do not claim those criteria passed before evidence exists | Phase 7, anytime |
| Tracing, application metrics and dashboards | Select a bounded trace pipeline, verify opted-in app span origins, collect application metrics privately and provision operator-only Grafana views; record source, cost, authorization and deployed evidence | Phase 4 |
| AI operations | Use only authorized Platform API context, including scoped telemetry; require evaluation and approval before writes | Phase 5 |
| Optional architecture expansion | Keep the single Python API and Kubernetes provider unless a concrete need justifies activating adapter or service-extraction work | Optional Phase 6 |
| Schema reuse | Fit-gap assessment of candidate projects | Before stabilizing v1 |
| Domains, versions, storage, alert recipients | Keep the deployed profile and source defaults explicit; capture exact live revision and recipient evidence | Before installation changes |
| RPO/RTO, retention, capacity | Backup policy is selected (24-hour RPO, four-hour RTO, 14/8/6 retention); [ADR-017](../../architecture/decisions/ADR-017-phase-1a-retention-evidence-scope.md) omits full-horizon retention evidence from Phase 1A, so measure recovery, retention, and capacity against targets | Before production-like acceptance |

[ADR-004](../../architecture/decisions/ADR-004-identity-and-access-management.md) resolves the identity-provider, Phase 1B role and realm-model decision: use a generic OIDC contract, Keycloak as the supported lab reference, and platform-owned project grants. Implementation and acceptance remain OPS-001/002/004 work; outstanding hosted-application client automation and richer access acceptance remain in Phase 7.

The project owner decides scope and ADRs; implementation and operations provide evidence. Specific delivery owners, dates, and capacity commitments remain unassigned; the project owner is the sole alert responder.

## Recording progress

For each completed work package and story criterion, record the date, repository revision, environment, test/demo results, and remaining limitations. Record and link evidence beside the relevant backlog task before closing a story; all its acceptance criteria must pass, including any deferred component-specific criteria. Record partial slices separately. Recheck authorization/audit and backup coverage whenever new endpoints, secrets, identities, revisions, or inventories are introduced. Update the roadmap and ADR when scope changes. A requested or generated artifact alone does not prove an operational system.
