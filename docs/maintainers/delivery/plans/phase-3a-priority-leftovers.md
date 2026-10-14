# Phase 3A — Priority Slice Completion

Status: active execution phase. This plan collects the remaining work in
`PLAN-016`, `PLAN-009`, `PLAN-017`, `PLAN-018`, and `PLAN-019`, plus the
deferred deployed portal acceptance for owner-accepted `PLAN-020`. It does not
replace their acceptance criteria or create a new task ID. The
[delivery backlog](../backlog.md) remains the authoritative task and evidence
register.

## Goal

Close the generic hosted-application use-case enablement slice with reproducible
deployed evidence. This phase finishes the neutral platform contract,
identity/access behavior, component-aware monitoring, the authenticated
provider/consumer integration gate, and recovery. It must remain
provider-neutral: concrete energy-system declarations and domain assertions are
owned and tested outside this repository.

## Entry and exit

Entry: Phase 2C is accepted and the decisions in
[ADR-020](../../../architecture/decisions/ADR-020-generic-hosted-application-integration.md)
are accepted.

Exit: every acceptance criterion for `PLAN-016`, `PLAN-009`, `PLAN-017`,
`PLAN-018`, and `PLAN-019`, and the deferred deployed portal journeys in
`PLAN-020`, has dated source, local, and deployed evidence (or a new explicit
owner-directed exception). The generic and externally owned versioned results
are recorded together. Only then may new general Phase 3 breadth (`PLAN-006`
through `PLAN-008`) start.

Existing EV-45 and EV-46 are partial evidence, not phase exit: they do not
prove the outage/recovery, elapsed-retention, IPv6, changed-DNS, or external
suite outcomes below.

## Ordered work packages

### 3A.1 — Close the neutral contract (`PLAN-016`)

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

### 3A.2 — Complete hosted-application identity acceptance (`PLAN-009`)

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

### 3A.3 — Complete monitoring and retention acceptance (`PLAN-017`)

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

### 3A.4 — Complete the generic integration gate (`PLAN-018`)

1. Run the neutral digest-pinned provider/consumer harness after 3A.1–3A.3.
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

### 3A.5 — Complete durability and recovery (`PLAN-019`)

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

### 3A.6 — Accept the deployed portal (`PLAN-020` follow-up)

The portal source is implemented; this package replaces the prior owner waiver
with executable, deployed acceptance. Run it against the same versioned portal,
Platform API, and reference identity deployment used for the relevant 3A checks.

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

## Evidence and handoff rules

- Record each package in the backlog verification register with date,
  environment, deployed revision, fixture/harness digest, commands/results, and
  limitations. Do not promote a local or source check to deployed acceptance.
- Preserve real backups and verified-success history when injecting bounded
  faults. Follow the existing lab policy; do not create an additional
  environment merely for this phase.
- A failed check returns work to its owning `PLAN-xxx`; record the remediation
  and rerun dependent packages in order.
- `PLAN-020` remains accepted for lab sequencing, but package 3A.6 closes its
  waived deployed browser/audit evidence before Phase 3A exit or a
  production-like portal claim.

## Dependencies

`PLAN-016` → `PLAN-009` → `PLAN-017` → `PLAN-018` → `PLAN-019`, with portal
acceptance package 3A.6 run after the identity/access API is available and before
Phase 3A exit.

`PLAN-018` requires the implemented and accepted identity, contract, and
monitoring outcomes. `PLAN-019` requires the completed deployed integration
gate. `PLAN-006` through `PLAN-008` remain blocked on Phase 3A exit.

Foundations: [energy-system priority plan](energy-system-integration.md),
[generic use-case enablement increment](use-case-enablement-increment.md),
[backlog](../backlog.md), and
[hosted-access validation procedure](../../../operators/validation/access-and-authorization.md).
