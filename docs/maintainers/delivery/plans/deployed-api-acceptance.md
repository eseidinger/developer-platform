# Deployed Platform API acceptance suite

Status: proposed plan, October 18, 2026. Documentation only; no new runner or
deployed result is claimed here.

## Objective and boundary

Create a repeatable, black-box API suite for a newly installed, disposable
Developer Platform. It sends real HTTP requests to the deployed API and OIDC
provider, waits for real Kubernetes-backed operations, and records the outcome
of each assertion and cleanup. This is the first installed-platform stage in
the [testing requirements](../../testing-requirements.md); CLI and UI stages
follow it. It does not replace the API unit and dependency-integration tests
that run in CI.

The suite tests the public API contract and externally observable effects. It
does not import `app.main`, connect directly to the platform catalog, or alter
Kubernetes resources to manufacture a pass. Separate operator probes may read
Kubernetes state when an API response alone cannot prove a requirement; such
checks must be named and reported separately from black-box API assertions.
Checks that require a configured period of elapsed time are excluded under the
[time-dependent test requirements](../../time-dependent-test-requirements.md).

## Existing coverage to preserve

[`test-platform.yml`](../../../../ansible/test-platform.yml) is the initial
parity baseline. It exchanges a test-runner credential, creates two empty
projects and viewer/developer/project-admin personas, proves role and
cross-project denials, deploys with a project-scoped credential, waits for a
ready operation, checks configuration, restart, rollback, diagnostics, recovery
request review, credential rotation and immediate revocation, then attempts
cleanup. The replacement must preserve every meaningful assertion before that
playbook is retired. The [component playbook](../../../../ansible/test-platform-components.yml),
[hosted-access harness](../../../../scripts/acceptance/check-hosted-access.py), and other
specialized drills remain distinct until their coverage is deliberately
incorporated.

The playbook's `always` cleanup suppresses errors. The new suite must report
cleanup as incomplete if credentials, personas, or projects remain, even when
all functional assertions passed.

## Runner contract

- A controller-side Python entry point offers `plan`, `run`, and `cleanup`.
  `plan` validates inputs and computes run-scoped names without contacting or
  changing the platform. `run` requires an exact API-origin confirmation and
  refuses a reused run ID. `cleanup` resumes only the resources recorded for
  that run.
- Inputs are an API origin, OIDC token endpoint, protected test-runner credential
  file, a fresh run ID, a digest-pinned neutral fixture image, and any required
  CA bundle. No password, secret, or bearer token appears in command arguments,
  Git, ordinary logs, or the public report.
- The runner obtains short-lived tokens through OIDC client credentials and
  refreshes them before expiry. It uses separate identities for the runner,
  personas, and deployment credential. The runner's platform-wide grant is not
  treated as proof of a project's narrower roles.
- Each assertion has a stable name, expected observation, observed safe status,
  duration, and result. Polling has a deadline and reports a failed operation
  distinctly from an operation that never became ready.
- A private mode `0600` journal records run-owned resource IDs and cleanup
  progress without raw credentials. A redacted JSON report records the source
  and installed revisions, API origin, fixture digest, capability profile,
  assertion results, skipped modules, and final cleanup state.
- The runner creates only run-scoped synthetic projects and data. It never
  targets an existing project or real application data. Normal cleanup revokes
  credentials and personas, retires the projects, and verifies the outcomes.
  Retained databases are reported explicitly; host disposal or a separate
  authorized purge handles their final removal.

Use the established `platform/acceptance` conventions for origin validation,
private files, fixed safe error codes, bounded waits, and redacted reports.
Extract small shared helpers if useful; keep this runner independent of the
hosted-access fixture's policy-specific flow. Unit tests for the runner's
validation, request handling, interrupted cleanup, and report redaction belong
in CI and require no installed platform.

## Baseline assertion matrix

| Module | Required deployed assertions |
| --- | --- |
| Installation and identity | `/healthz`, `/readyz`, public capabilities and expected API contract; missing, malformed, and wrong-audience tokens denied; real OIDC token exchange succeeds for each test identity. Compare the installation record with the intended source revision before the run. Natural token expiry belongs to the timed suite. |
| Scope and roles | Create two empty projects. Viewer sees only its project and cannot deploy, change configuration, or grant roles. Developer can change/deploy its project but cannot manage grants or retire it. Project administrator can manage its own project but not the other. Test runner has the documented platform privileges but cannot create another root runner. |
| First deployment | Create a project deployment credential as project administrator; exchange its secret for a token; submit the first deployment; follow the durable operation to success and readiness; verify the application through its declared public route. Prove the deployment credential cannot read the foreign project or administer credentials. |
| Revisions and diagnostics | Change configuration, restart, and roll back; verify revision and operation relationships, readiness, logs, drift, resource inventory, and resource usage. Check meaningful response fields and effects rather than only HTTP `200`. |
| Secrets and recovery | Create and rotate a synthetic write-only secret; verify metadata and activation without exposing its value; exercise confirm/revert where supported. Create a developer-visible recovery request, review it with platform authority, and verify the safe viewer-visible outcome. |
| Credentials and audit | Rotate the deployment credential, inspect overlap metadata, prove both generations work immediately after rotation, explicitly revoke the predecessor, and prove its already-issued token is denied on the next request. Verify redacted audit events for representative allowed, denied, and privileged actions. The overlap deadline itself belongs to the timed suite. |
| Retirement and cleanup | Preview and retire only run-owned projects; verify workload access and old credentials are denied, temporary personas and credentials are revoked, and cleanup status reflects every remaining resource. |

The matrix is a starting baseline, not a claim that the complete platform is
covered. Before implementation, map each assertion to an API operation, a
documented expected result, a fixture, and an evidence field. Mark unsupported
or optional capabilities explicitly rather than passing them through omission.

## Additional tests by platform capability

The baseline above establishes a small healthy project and the core role matrix.
Add the following modules without hiding their prerequisites. Each module needs
at least one allowed path, one denied or invalid path, a real observable effect,
and run-scoped cleanup. Reuse the same two-project boundary where possible, but
give stateful modules their own fixture resources so their failures do not mask
one another.

### Application deployment and lifecycle

| Capability | Additional assertions | Existing starting point |
| --- | --- | --- |
| Versioned declarations and operations | Deploy a `v1alpha2` application; reject an invalid component or unsupported field before a revision or workload appears; repeat an identical request without duplicate effects; reject stale `If-Match`; distinguish accepted, failed, and ready operation states. | [Component playbook](../../../../ansible/test-platform-components.yml), API unit tests. |
| Multiple services and scheduled declarations | Deploy two communicating services and declare a scheduled component; verify separate component status and resource inventory, reject an invalid schedule, and update one service without rolling its peer. Observing a scheduled fire, recurring cadence, or `Forbid` non-overlap belongs to a separate timed run. | [Component playbook](../../../../ansible/test-platform-components.yml). Raw Kubernetes evidence remains a separately named operator probe. |
| Configuration and secrets | Verify new configuration reaches the workload; reject reserved or secret-like configuration names; set/rotate/confirm/revert a write-only secret and verify activation; reject unauthorized secret changes and prove values do not appear in reads, revisions, logs, or audit export. | [Core playbook](../../../../ansible/test-platform.yml), [rollback-data playbook](../../../../ansible/test-platform-rollback-data.yml). |
| Restart, rollback, and drift | Restart without creating a new desired revision; roll back to a retained revision and verify the running behavior; confirm rollback preserves the current data and secret generation; introduce a controlled drift and observe it through the API before reconciliation. | [Core playbook](../../../../ansible/test-platform.yml), [rollback-data playbook](../../../../ansible/test-platform-rollback-data.yml). Controlled drift injection needs a separate operator probe. |
| Routing and connectivity | Check the declared public URL over TLS, private-component non-exposure, route removal after a private revision, internal service discovery, and denial of unapproved outbound destinations; an approved destination must have a successful positive control. | [Component playbook](../../../../ansible/test-platform-components.yml), [egress playbook](../../../../ansible/test-platform-egress-policy.yml). Network denial needs a real workload or operator probe, not an API status alone. |
| Resource policy and capacity | Reject invalid quotas and requests before side effects; inspect effective security configuration and `/operator/capacity`; verify accepted workloads fit the declared limits. Run reservation/admission pressure only in an isolated capacity module that restores settings. | [Capacity playbook](../../../../ansible/test-platform-capacity-admission.yml). |

### Identity, authorization, and hosted access

| Capability | Additional assertions | Existing starting point |
| --- | --- | --- |
| Grants and credential lifecycle | Test grant add/change/revoke for each role, platform-admin scope, cross-project denial on every new data surface, test-runner inability to mint another root runner, one-time client-secret disclosure, immediate revocation, and audit attribution. Verify the same valid token loses authority immediately after grant revocation. Natural expiry belongs to a timed suite. | [Core playbook](../../../../ansible/test-platform.yml), [human access runbook](../../../operators/validation/access-and-authorization.md). Human browser or device login is not proved by a service-account persona. |
| Hosted application policy | On a public `v1alpha2` fixture, create governance and groups, reject invalid or overlapping route rules, activate and roll back a policy, and verify unmatched or wrong-method requests are denied. Check that platform project grants alone do not confer application-group access. | [Hosted-access harness](../../../../scripts/acceptance/check-hosted-access.py). Its live human and machine access assertions remain authoritative until incorporated with equal depth. |
| Hosted application membership and machine access | Exercise pending human request, approval, group assignment and revocation; request and approve consumer-project service access; verify audience/group scoping, one-time managed credential metadata, rotation/adoption, and denial of a still-valid token after revocation. Include same-project consumer access. | [Hosted-access harness](../../../../scripts/acceptance/check-hosted-access.py). Browser cookie and CSRF checks need its browser-capable HTTP fixture, not a persona token. |
| Operator audit and inspection | Query scoped permission and security views with platform authority; deny project members; export a bounded, redacted audit window; correlate actor, target, outcome, revision or operation ID for representative success and denial events. | [Core playbook](../../../../ansible/test-platform.yml), [human access runbook](../../../operators/validation/access-and-authorization.md). |

### Data services and persistence

| Capability | Additional assertions | Existing starting point |
| --- | --- | --- |
| PostgreSQL resource and binding | Create a named resource, bind it explicitly to a component, and prove a fixture can write and read a marker. Deny foreign-project access; verify explicit credential rotation and revocation, and prove application rollback does not erase the marker. Confirm an unbound component receives no database credential. Lease expiry belongs to a timed suite. | [Named PostgreSQL fixture](../../../../scripts/verify/stores/verify-named-postgres.py), [human database harness](../../../../scripts/acceptance/check-human-database-access.py), [rollback-data playbook](../../../../ansible/test-platform-rollback-data.yml). Native SQL assertions must remain alongside API checks. |
| Human database access | Create an individual grant and verify the authorized person's lease, read-only SQL access, foreign-database denial, key replacement, password rotation, and session termination after revocation. A test persona may help with API setup but cannot prove human login or an SSH tunnel. | [Human database harness](../../../../scripts/acceptance/check-human-database-access.py). Requires the separately installed restricted bastion and trusted host key. |
| Resource retirement and purge | Retire a run-owned application and named resource; verify route, binding, and credential denial while retained data remains accounted for. Exercise preview tokens, stale scope rejection, and final purge only in an explicitly isolated disposable-data module. | [Core playbook](../../../../ansible/test-platform.yml), store-specific fixtures. Purge must never target an unverified resource. |
| Analytics artifacts | Where the S3 profile is enabled, write a small synthetic Parquet artifact from a bound workload, read it through the intended consumer path, and deny an unrelated project. Verify that the artifact survives an application revision rollback and that explicit credential revocation denies access. Retention duration belongs to a timed suite. | [Analytics artifact example](../../../../examples/analytics-artifacts/README.md) and the RustFS fixture. |
| Selected S3, vector, search, and graph stores | For each enabled provider, create a resource, bind a neutral consumer, perform a native write/read, test a foreign-project denial, rotate or revoke access, and verify resource isolation and retirement. Record provider-specific limitations rather than treating a generic API `200` as a successful native operation. | [Store validation procedures](../../../operators/data-stores.md#local-verification) and their disposable provider fixtures. Run only for installed profiles. |

### Observation and controlled actions

| Capability | Additional assertions | Existing starting point |
| --- | --- | --- |
| Diagnostics and telemetry | Emit a run marker and verify project/component logs, retained-log cursor and redaction, resource/usage state, application metrics, and trace lookup. Prove a foreign-project principal cannot read the marker or trace. Check that unavailable telemetry is reported as unavailable rather than healthy or empty. Do not claim elapsed retention. | [Component playbook](../../../../ansible/test-platform-components.yml), [monitoring guide](../../../operators/monitoring.md), telemetry fixture checks. |
| AI assistance and approved changes | When a model provider and budget are configured, create a run with attributable evidence, inspect scoped history, create a proposal, reject an unapproved or stale proposal, approve the exact reviewed hash, and execute once through a durable operation. Prove foreign-project denial and that automation lacks human-only approval authority. | [AI API tests](../../../../platform/app/tests/test_ai_operations.py) and [AI approval guard fixture](../../../../scripts/verify/ai/verify-ai-approval-guards.py). A configured external model is an explicit optional prerequisite; local stubs alone are not deployed-model evidence. |
| Recovery requests and lifecycle failure | Prove developer request, operator acknowledgement/resolution, safe viewer-visible result, and recovery after an induced PostgreSQL failure. Keep actual service interruption in a separate drill with restoration in `always` cleanup. | [Core playbook](../../../../ansible/test-platform.yml), [PostgreSQL outage playbook](../../../../ansible/test-platform-postgres-outage.yml). |

### Module selection and reporting

Baseline modules run on every newly installed platform. Multi-service and
scheduled-resource declaration, hosted access, named PostgreSQL, and observability should be
added to the standard installed profile once their fixtures and dependencies
are ready. Optional store providers and model-backed AI run only when their
profiles are selected. Read the public capabilities and the installation's
selected provider profile before deciding which modules apply; if those sources
disagree, fail the preflight instead of skipping a test. Every skip records a
specific unmet prerequisite. A required module that cannot start is a failure.

Preserve specialized live checks that inspect native SQL, Bolt, S3, search, or
cluster behavior until an equivalent module exists. Backup restore, service
outages, external notifications, and all elapsed-time checks are separate
explicitly scoped drills, not implicit API baseline passes. The module report
should list the API result and any native/operator evidence separately so a
passing endpoint response cannot conceal a failed workload or provider.

## Minimum manual handoff

The [testing requirements](../../testing-requirements.md#minimum-manual-setup-for-a-disposable-run)
record the current manual path. For the first implementation, an operator
provides a disposable host, DNS/TLS and SSH access, chooses the capability
profile, deploys with Ansible, bootstraps one human administrator and the
expiring test runner, and supplies the protected runner file and fixture
digest. The API suite then needs one offline `plan` and one explicit `run`;
cleanup is automatic on normal completion and separately retryable after
interruption. A later installation orchestrator may reduce the manual setup,
but it must preserve the same test and evidence contracts.

The requested disposable installation revisits
[ADR-010](../../../architecture/decisions/ADR-010-single-environment-lab.md),
which rejected a standing extra lab. Record the updated environment decision
before provisioning one; this plan itself does not provision it.

## Implementation sequence and exit criteria

1. Specify the assertion-to-endpoint inventory and the baseline fixture. Review
   the exact parity list against `test-platform.yml` and identify stronger
   checks for secret handling, public routing, and cleanup.
2. Implement the runner contract and its CI tests for offline plan, invalid
   inputs, redaction, resource ownership, interrupted cleanup, and reporting.
3. Implement the baseline deployed modules, run them on a newly installed
   disposable platform, and record a complete report. Keep the Ansible playbook
   available for comparison during this stage.
4. Retire `test-platform.yml` as the primary baseline only after every preserved
   assertion passes in the new suite and a failed-cleanup case is visibly
   reported. Update the operator procedure to invoke the new entry point.
5. Add capability modules separately, each with its own prerequisites, checks,
   cleanup, and evidence. Then let CLI and UI acceptance reuse the installation
   and run-scope contract without treating API success as their success.

The baseline is complete when a clean disposable installation produces a
redacted report with all required checks passed, no unexplained skips, verified
identity/project cleanup, and an explicit retained-data disposition. Failed
assertions or incomplete cleanup must produce a nonzero result and actionable
safe check names. No CI result or historical lab run substitutes for this new
deployed result.
