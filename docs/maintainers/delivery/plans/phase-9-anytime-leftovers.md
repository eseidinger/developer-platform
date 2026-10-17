# Phase 9 — Anytime Leftovers

Status: unscheduled, lowest-priority phase. It is listed last in the delivery
plan and may be worked on whenever capacity allows; it does not gate Phases 3,
4, 5, or optional 6. Internal dependencies still apply when a package is run.
This plan collects the remaining work in
`PLAN-016`, `PLAN-009`, `PLAN-017`, `PLAN-018`, `PLAN-019`, `PLAN-006`,
`PLAN-007`, and `PLAN-008`, plus the deferred deployed portal acceptance for
owner-accepted `PLAN-020`, and all deferred acceptance/fixes from owner-completed
Phase 4 (`PLAN-021`–`PLAN-024`, package 9.9), and deferred second AI model
provider evaluation (`PLAN-012` follow-up, package 9.10). It does not replace their acceptance criteria or
create a new task ID. The
[delivery backlog](../backlog.md) remains the authoritative task and evidence
register.

## Goal

Close the generic hosted-application use-case enablement slice with reproducible
deployed evidence. This phase finishes the neutral platform contract,
identity/access behavior, component-aware monitoring, the authenticated
provider/consumer integration gate, and recovery, plus deferred Phase 4 telemetry
acceptance and second AI model-provider evaluation. It must remain
provider-neutral: concrete energy-system declarations and domain assertions are
owned and tested outside this repository.

## Entry and exit

Entry: Phase 2C is accepted and the decisions in
[ADR-020](../../../architecture/decisions/ADR-020-generic-hosted-application-integration.md)
are accepted.

Exit: every acceptance criterion for `PLAN-016`, `PLAN-009`, `PLAN-017`,
`PLAN-018`, `PLAN-019`, `PLAN-006`, `PLAN-007`, and `PLAN-008`, and the
deferred deployed portal journeys in `PLAN-020`, Phase 4 follow-ups in package 9.9,
and second AI model-provider evaluation in package 9.10, has dated source, local, and
deployed evidence (or a new explicit owner-directed exception). The generic and
externally owned versioned results are recorded together. Only then may Phase 9
be closed; incomplete work here remains visible without blocking the other
phases.

Existing EV-45 and EV-46 are partial evidence, not phase exit: they do not
prove the outage/recovery, elapsed-retention, IPv6, changed-DNS, or external
suite outcomes below.

## Ordered work packages

### 9.1 — Close the neutral contract (`PLAN-016`)

1. Add or verify neutral digest-pinned `provider` and `consumer` `v1alpha2`
   declarations with a public API, private worker, readiness checks, bounded
   resources, separate managed PostgreSQL databases, and explicit DNS/443
   consumer egress.
2. Add contract tests for derived public hostnames, egress address pinning and
   explicit reapply, digest use, database separation, readiness/resource
   validation, secret redaction, and rejection of undeclared cross-project or
   unsupported identity inputs.
3. Validate project governance records for classification, personal-data
   handling, domain-retention owner/policy, purge authority, and recovery owner.
4. Regenerate/check the API contract and verify documentation, links, and
   capability advertising describe only implemented behavior.

**Exit evidence:** neutral fixtures and tests pass; no fixture, API behavior, or
default is energy-application-specific; every unsupported capability remains an
explicit rejection or accepted ADR-020 limitation.

### 9.2 — Complete hosted-application identity acceptance (`PLAN-009`)

1. Use the generic access resources to run the remaining browser and machine
   authentication/authorization cases against the deployed reference boundary.
2. Exercise identity-provider/control-plane dependency outage while an
   authorizer snapshot is valid, then prove fail-closed behavior after the
   five-minute bound and safe restored access after reconciliation.
3. Exercise remaining time- and lifecycle-bound behavior: browser idle and
   absolute expiry, claim refresh/staleness, normal 24-hour rotation overlap,
   request retention/pruning, audit lifecycle, and backup/recovery coverage.
4. Verify restored/recreated human and service identities have no inherited
   memberships, and retain redacted evidence for policy, group, membership,
   credential, revocation, retirement, and recovery transitions.
5. Fix implementation or automation only where these checks expose a defect;
   rerun the full relevant regression and deployed suite after each fix.

**Exit evidence:** all `PLAN-009` acceptance bullets pass, including outage and
restored-access behavior; platform/project/deployment roles never grant an
application group implicitly.

### 9.3 — Complete monitoring and retention acceptance (`PLAN-017`)

1. Keep component-aware protected-boundary probes, workload semantic readiness,
   and central Kubernetes log collection under the neutral fixtures.
2. Demonstrate authorized central-log readback after workload restart and
   retirement, preserving project/component scope and redaction.
3. Run and record the configured seven-day Loki retention/compactor interval;
   show that expired data is removed according to policy without broadening
   project access.
4. Record probe, collector, Loki, and API revisions/configuration with the
   deployed result; correct any collection or retention failure and repeat the
   affected evidence.

**Exit evidence:** deployed component probes, semantic readiness, safe central
correlation, post-restart/retirement reads, and elapsed seven-day retention all
pass.

### 9.4 — Complete the generic integration gate (`PLAN-018`)

1. Run the neutral digest-pinned provider/consumer harness after 9.1–9.3.
   Capture image digests, revisions, routes, readiness, resource bounds, safe
   correlation, TLS, and resolved egress addresses.
2. Verify allowed browser and pre-authorized service flows and the full denied
   matrix, including missing/expired/wrong-audience tokens, pending or
   wrong-group identities, forged headers, direct backend access, unrelated
   egress, and both IPv4 and IPv6 isolation.
3. Change the approved DNS result, prove existing pinning does not silently
   widen access, explicitly reapply, and verify the newly recorded addresses.
4. Obtain and record the immutable, versioned externally owned energy-system
   suite result. Do not copy its declarations, data, or domain authorization
   assertions into platform source.

**Exit evidence:** the complete generic deployed gate and separately owned
external result are both recorded, versioned, and reproducible.

### 9.5 — Complete durability and recovery (`PLAN-019`)

1. Take a verified backup after the neutral integration state is active and
   record the snapshot, platform revision, fixture/image digests, and contract
   version.
2. Restore through the supported isolated recovery workflow. Verify recovered
   application resources, retained and isolated database data, principals,
   groups, memberships, policies, identity bindings, routes, TLS, and managed
   credential recovery/rotation handling.
3. Reconcile outward from the restored PostgreSQL-authoritative catalog; keep
   protected routes unavailable until identity resources and policy replicas are
   ready, then verify restored allowed and denied access.
4. Re-run the immutable external workflow with its required reapplication and
   record its reference result, recovery duration, database checks, route/TLS
   result, and manual identity steps beside the generic result.

**Exit evidence:** a real backup restoration—not a marker readback or restart
alone—reproduces generic and external reference results with the required
authorization and isolation checks.

### 9.6 — Accept the deployed portal (`PLAN-020` follow-up)

The portal source is implemented; this package replaces the prior owner waiver
with executable, deployed acceptance. Run it against the same versioned portal,
Platform API, and reference identity deployment used for the relevant Phase 9 checks.

1. Sign in through the real OIDC flow and exercise viewer, developer,
   project-administrator, and platform-administrator views. Verify direct API
   requests deny actions that are absent or disabled in the portal.
2. Create or update a project application, follow its operation/readiness, and
   diagnose an injected failure using status, inventory/resource observations,
   component/instance/time-filtered logs, and the URL-persisted log filters.
   Exercise validation, stale-revision conflict, provider-unavailable, and
   authorization-denied states.
3. Through **Application access**, create groups and governance metadata; define
   and activate a structured policy; observe a pending human first-login denial;
   approve group membership; verify admitted access after refresh; and revoke it
   within the accepted bound.
4. Request consumer service access, approve provider bearer groups, verify the
   active managed binding and allowed call, then exercise normal/emergency
   rotation, explicit adoption, and owner-authorized revocation. Verify
   wrong-group, cross-project, and unauthorized direct API attempts are denied.
5. Inspect browser storage, network/error output, audit-safe views, screenshots,
   and test artifacts to prove no secret, access token, or managed credential
   value is exposed. Include keyboard/focus and failure/pending-state checks for
   the touched controls.

**Exit evidence:** dated browser and audit records demonstrate the portal
journeys above, identify the deployed portal/API revisions, and distinguish UI
behavior from the server-side access enforcement already established by the
generic harness.

### 9.7 — Accept general self-service delivery (`PLAN-006`–`PLAN-008`)

Source implementation for the portal/CLI, reusable web/PostgreSQL template, and
human database access belongs to Phase 3. This package owns all deployed
acceptance for those capabilities.

1. Run the documented role matrix through both portal and CLI: human OIDC login,
   deployment-credential automation, authorized discovery and diagnosis,
   configuration/secret lifecycle, recovery request, rollback/restart,
   retirement, grants, and credential lifecycle. Prove every disallowed action
   remains denied by a direct Platform API request.
2. Create, deploy, diagnose, update, and retire the reusable web/PostgreSQL
   template using the same versioned application declaration from portal and
   CLI. Record API, template/image, and client versions plus the injected-failure
   result.
3. Exercise human database access with distinct human and workload credentials:
   authorized tunnel establishment, foreign-project denial, audited creation/use/
   revocation, and termination of new and existing sessions according to the
   published policy. EV-47 records the owner-accepted passing core checks;
   the remaining manual reviews are scheduled in the final work package below.

**Exit evidence:** repeatable deployed portal, CLI, template, and human-database
journeys pass against the recorded revisions, subject to the accepted EV-47
no-rerun decision. This evidence, rather than a source build or UI fixture,
establishes the functional portion of `PLAN-006`–`PLAN-008`; the final reviews
or an explicit owner-directed exception are still required to close `PLAN-008`.

### 9.9 — Complete deferred Phase 4 acceptance

**Unscheduled, lowest priority; non-gating for Phase 5.** On October 16, 2026,
the owner closed Phase 4 at baseline `4681e56` and moved all remaining checks
and resulting implementation fixes here. These are follow-ups to `PLAN-021`
through `PLAN-024`, not new task IDs or evidence that unperformed tests passed.
VEF/ODIP dashboard checks, PostgreSQL and host storage panels, and the recorded
local/live metric readback are already accepted; do not repeat those solely
because acceptance moved phases.

- [ ] **Tracing (`PLAN-021`, `PLAN-024`):** Follow API → durable worker → provider
  outcomes and application-to-application traces. Cover allowed/denied requests,
  successful/failed operations, interruption/retry, scheduled work, and sampled
  coverage across the recorded framework images. Correct any missing trace path.
- [ ] **Security (`PLAN-021`, `PLAN-023`, `PLAN-024`):** Verify project-scoped metric
  and trace reads, cross-project denial, forged context/resource-origin rejection,
  and secret/PII redaction in stored spans, metrics, links and evidence.
- [ ] **Sampling (`PLAN-021`, `PLAN-024`):** Exercise 0%, the 10% default and temporary
  100% fixture sampling; check root decisions and downstream behavior, distinguish
  sampling gaps from collection failure, and restore normal settings.
- [ ] **Failure/recovery (`PLAN-021`–`PLAN-024`):** Inject bounded application and
  telemetry collector/backend failures. Show useful no-data/error states, continued
  application/deployment operation and authorization, and collection recovery.
- [ ] **Lifecycle (`PLAN-023`, `PLAN-024`):** Verify retirement removes metric targets,
  revokes trace submissions and preserves the intended scoped historical reads.
- [ ] **FastAPI runtime (`PLAN-023`, `PLAN-024`):** Deploy an instrumented FastAPI
  fixture and verify metrics, selectors and traces. Existing synthetic Prometheus
  convention tests remain local evidence, not deployed framework acceptance.
- [ ] **Operational acceptance (`PLAN-021`–`PLAN-024`):** Verify fresh-start/restart
  provisioning and reconciliation; safe trace/log/operation links; application and
  component switching without mixed/stale signals; redacted artifacts and exact
  backend, collector, dashboard and fixture revisions. Measure resource cost and
  confirm ingestion/cardinality limits, 24-hour trace retention, the 4 GiB trace
  filesystem and shared monitoring storage budgets, recording elapsed checks
  separately from configuration. Keep the existing seven-day Loki check in 9.3.

**Exit evidence:** each unchecked outcome has dated source/local/deployed results
and limits, or a new explicit owner exception. Repair defects discovered during
these checks and rerun affected verification. Phase 4 stays closed for delivery
sequencing; these outcomes remain unverified until executed. Run this package
when capacity allows, before the final human-database reviews in 9.8; its number
preserves existing package references rather than imposing numeric execution order.

<a id="ai-model-provider-leftovers"></a>

### 9.10 — Verify a second AI model provider (`PLAN-012` follow-up)

**Unscheduled, lowest priority; non-gating for Phase 5.** On October 16, 2026,
the owner moved second-provider setup, adapter work and evaluation here. No
second account, endpoint or credential is required for the current Phase 5 gate.
The implemented provider-neutral boundary remains; interoperability with another
provider has not been demonstrated. Existing primary-provider synthetic and live
acceptance evidence remains valid, and this deferral is not a passing test.

1. Select an available second provider/account or local endpoint. Verify its
   model access, data-handling eligibility and applicable terms before use;
   configure credentials through protected operator storage.
2. Implement any required adapter while preserving project scope, classification,
   redaction, tools-disabled finalization, approval separation and error handling.
3. Run the same versioned corpus and thresholds, including known diagnoses,
   insufficient evidence, untrusted input and project boundaries. Record cost,
   latency, tool budgets and safe trace coverage without raw model content.
4. Record provider/model/adapter versions and compare outcomes with the accepted
   primary-provider baseline. Fix contract or safety regressions and rerun the
   affected checks.

**Exit evidence:** a second provider passes the unchanged quality, abstention,
budget and safety contracts, with dated reproducible evidence and documented
limits, or a new explicit owner-directed exception. Schedule independently when
capacity and a provider setup are available, before the final reviews in 9.8.

### 9.8 — Complete the lowest-priority human database leftovers (`PLAN-008`)

Schedule this **last**, after all other Phase 9 work packages, including 9.9 and 9.10. EV-47's
automated and manual core tests are accepted as passed and need no repeat solely
for the later clean deployment. The following reviews remain unverified:

1. Review the remote firewall boundary for the restricted bastion, beyond the
   recorded failed external connection to its loopback-only port.
2. Inspect browser storage after the human database credential, SSH key, and
   revocation journey for retained tunnel secrets or SQL passwords.
3. Independently review client output, logs, audit exports, screenshots, and
   saved evidence for unintended tunnel-secret or SQL-password exposure.

**Exit evidence:** record the three review results and their limits against the
deployed revision, or record an explicit owner-directed exception naming each
unverified review. This is the last priority in this plan; moving it here does
not turn an unperformed check into a passing result.

## Evidence and handoff rules

- Record each package in the backlog verification register with date,
  environment, deployed revision, fixture/harness digest, commands/results, and
  limitations. Do not promote a local or source check to deployed acceptance.
- Preserve real backups and verified-success history when injecting bounded
  faults. Follow the existing lab policy; do not create an additional
  environment merely for this phase.
- A failed check returns work to its owning `PLAN-xxx` follow-up; owner-completed
  Phase 4 delivery tasks remain closed while their fixes stay in package 9.9. Record the remediation
  and rerun dependent packages in order.
- `PLAN-020` remains accepted for lab sequencing, but package 9.6 closes its
  waived deployed browser/audit evidence before Phase 9 exit or a
  production-like portal claim.

## Dependencies

`PLAN-016` → `PLAN-009` → `PLAN-017` → `PLAN-018` → `PLAN-019`, with portal
acceptance package 9.6 run after the identity/access API is available. Package
9.7 runs after the Phase 3 source capabilities are ready. Run 9.8 last,
after 9.1–9.7, 9.9 and 9.10; its reviews or an explicit owner-directed exception remain
required before Phase 9 exit. Package 9.9 can run independently once the
implemented Phase 4 telemetry is available and does not gate Phase 5.
Package 9.10 runs once a second model-provider setup is available and also does
not gate Phase 5; primary-provider acceptance does not depend on its completion.

`PLAN-018` requires the implemented and accepted identity, contract, and
monitoring outcomes. `PLAN-019` requires the completed deployed integration
gate. Source implementation for `PLAN-006` through `PLAN-008` may proceed in
Phase 3; their remaining acceptance belongs to packages 9.7 and 9.8.

Foundations: [energy-system priority plan](energy-system-integration.md),
[generic use-case enablement increment](use-case-enablement-increment.md),
[backlog](../backlog.md), and
[hosted-access validation procedure](../../../operators/validation/access-and-authorization.md).
