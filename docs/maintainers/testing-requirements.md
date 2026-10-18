# Testing requirements

Status: draft for discussion, October 18, 2026. This document records the desired
test boundaries and identified gaps; it does not report new acceptance evidence.

## Goals

1. Run automated tests for the Platform API, CLI, and UI in CI for every behavior
   that can be verified without a fully installed platform.
2. Run a separate automated acceptance suite against a newly installed,
   disposable platform to verify the assembled system through the API, CLI,
   and UI.
3. Make coverage and omissions explicit. A passing fixture test must not be
   reported as proof of a deployed journey.

## Delivery order for installed-platform tests

Build the deployed tests in this order. Each stage uses the same installation
contract and run-scoped fixtures; it must be able to run independently after its
prerequisites are met.

1. **Platform API first.** Install a disposable platform and exercise the real
   public API, Keycloak, PostgreSQL, Kubernetes operations, and application
   routing. Start with readiness, identity bootstrap, the project-role and
   cross-project matrix, empty-project creation, first deployment, operation
   completion, diagnostics, configuration, secrets, restart, rollback,
   credential rotation/revocation, retirement, and redacted audit evidence.
   Record which optional capabilities were installed and tested. Reuse existing
   acceptance playbooks and harnesses where they meet these assertions.
2. **CLI second.** Run the installed `devplat` against that API and repeat the
   representative lifecycle and role-denial assertions through CLI commands.
   Verify JSON output and exit codes. Use test personas for machine-role checks
   and a separate human account for the device-login journey.
3. **UI third.** Run Playwright against the portal delivered by that platform,
   using human Keycloak users and real browser redirects. Check the main project
   journey, role-dependent controls, API denials, logout, and revocation. Keep
   the fixture-backed browser tests in CI for faster and broader UI states.

The API stage is the next implementation milestone. CLI and UI stages must not
be counted as passed merely because the API stage succeeds.
Its proposed implementation is the [deployed API acceptance suite plan](delivery/plans/deployed-api-acceptance.md).

## Test boundaries

| Suite | Environment | Required evidence |
| --- | --- | --- |
| CI | Source checkout with isolated processes and disposable dependencies such as PostgreSQL, Keycloak, and store containers. No complete platform installation. | Unit, component, contract, browser-fixture, and dependency-integration results; builds and configuration checks. |
| Installed-platform acceptance | A newly installed, disposable platform with its normal API, portal assets, identity provider, routing, Kubernetes workloads, and selected services. | Real API, installed CLI, and browser journeys against the same installation, with a recorded revision and cleanup result. |

The portal is part of the normal platform delivery. Neither suite needs a
separately installed portal service. CI builds and tests the UI source; installed
acceptance uses the portal served by the installed Platform API.

## CI requirements

- **API:** Test validation, authorization, revocation, durable state, migrations,
  audit/redaction, and provider adapters. Use real disposable dependencies where
  they establish behavior that mocks cannot. Check that the committed OpenAPI
  contract matches the application.
- **CLI:** Test every command family's request mapping, output and exit codes,
  authentication selection, permission-denial handling, concurrency behavior,
  and protection of one-time secrets. Keep the generated CLI contract in sync
  with OpenAPI. Exercise suitable client/API interactions against disposable
  dependencies without requiring a platform installation.
- **UI:** Test components and the main browser journeys with deterministic API
  fixtures: project discovery, creation, deployment, operation progress,
  diagnostics, configuration and secrets, restart, rollback, retirement,
  grants, and applicable access workflows. Cover loading, error, conflict,
  denial, keyboard, and narrow-screen states. Check generated API types, lint,
  type safety, and the production build.
- **Test tooling:** Check acceptance-runner plans, input validation, report
  formats, scoped cleanup logic, and Ansible syntax without claiming that the
  live procedures ran.

CI integration tests may start individual real services. They do not need to
start the entire Compose/k3d platform. Label unit, integration, and fixture
browser results distinctly.

## Installed-platform acceptance requirements

- Install the platform from a known revision into an isolated, disposable
  environment; record the installation revision, CLI version, UI artifact,
  fixture image digests, and enabled capabilities.
- Bootstrap dedicated human Keycloak users and an expiring test runner through
  protected test inputs. Use temporary test personas for API and CLI role tests.
  Use human users for browser PKCE login and human CLI device login.
- Exercise a shared project lifecycle through direct API requests, `devplat`,
  and the deployed portal. Check permitted and denied actions for viewer,
  developer, project administrator, and platform administrator, including
  cross-project access and revocation while a token is still valid.
- Verify real workloads, public routing, persisted data where applicable,
  operation status, diagnostics, and cleanup. Run capability-specific modules
  only for installed optional services; report skipped capabilities explicitly.
- Use a run ID and a resource ledger. Revoke temporary identities, retire or
  purge run-owned resources according to their retention contract, and make
  interrupted cleanup retryable. Produce a redacted machine-readable report
  that distinguishes assertion failure from incomplete cleanup.

Destructive outage, backup/restore, external notification, and long-duration
expiry checks need separately scoped modules and dependencies. Passing the core
journey does not imply that those modules passed.
The routine deployed API suite omits all checks that require a configured
period to elapse; see [time-dependent test requirements](time-dependent-test-requirements.md).

## Minimum manual setup for a disposable run

Document the smallest operator handoff needed for each test profile. The
following is the **current** path to a first deployed API run, assembled from
existing procedures; there is not yet a single acceptance command that performs
all of it:

1. Provide a disposable Ubuntu 22.04+ host with the documented capacity, SSH
   and sudo access from a trusted controller, resolvable platform/identity and
   wildcard application domains, and the required firewall and registry access.
   Choose the enabled store profile before installation. Use no existing
   application data.
2. From the intended source revision, create a protected Ansible inventory from
   [`ansible/inventory.example.yml`](../../ansible/inventory.example.yml). Set
   the host, SSH user, domains, TLS email, edge bind address, and selected
   provider/network settings. Run [`ansible/deploy.yml`](../../ansible/deploy.yml).
   On a fresh identity store, its final API readiness check may fail until the
   first administrator grant is bootstrapped; verify Keycloak and continue with
   step 3 before claiming installation readiness.
3. In the new Keycloak `platform` realm, create a dedicated initial human
   administrator, record its immutable subject privately, set
   `PLATFORM_BOOTSTRAP_SUBJECT` using the documented deployment procedure, and
   start/recreate the API to persist the one-time grant. Verify readiness,
   then remove that setting from the runtime environment. Obtain a short-lived
   human token through the documented PKCE flow.
4. Use the human token once with
   [`bootstrap-platform-test-runner.yml`](../../ansible/bootstrap-platform-test-runner.yml).
   Keep its one-time output outside the repository in a protected mode `0600`
   file on the controller. The existing initial API suite is
   [`test-platform.yml`](../../ansible/test-platform.yml), invoked with that
   protected runner file; additional API modules have their own prerequisites.
5. Record the API origin, source and installation revisions, enabled
   capabilities, test-run ID, result, and cleanup status. Retire the disposable
   installation only after checking for retained run data and unfinished
   identity or project cleanup.

The planned runner should automate steps 2–5 after the operator supplies the
host, DNS/TLS configuration, selected profile, and protected bootstrap inputs.
In particular, it should create and remove its own test accounts, obtain
temporary credentials without printing them, select fixture images by immutable
digest, run the API stage, and write a redacted report. The CLI and UI stages
should reuse that setup rather than require another manual bootstrap.

## Current coverage and gaps

The [API workflow](../../.github/workflows/platform-app.yaml) runs broad Python
tests, a PostgreSQL service, and selected real Keycloak checks. The
[CLI workflow](../../.github/workflows/cli.yaml) checks its generated contract,
mocked command behavior, and package build. The [UI workflow](../../.github/workflows/ui.yaml)
runs static checks, component tests, and Playwright against local Vite with API
fixtures. Separate workflows exercise disposable named-store and telemetry
dependencies. These are useful checks and should remain in CI.

The immediate CI gaps are a fixture-backed UI browser journey for the core
project lifecycle and broader CLI command-family behavior checks. The immediate
deployed-test gap is an API acceptance runner with a documented minimal setup,
followed by CLI and UI stages on the same installation. Existing live playbooks
and harnesses provide parts of that runner, but CI currently syntax-checks
rather than executes most platform acceptance playbooks. A passing CI run does
not close installed-platform acceptance.

## Decisions to settle

1. Define the baseline installed profile and the optional capability profiles
   whose full functionality each acceptance run must cover.
2. Decide when installed-platform acceptance runs and whether it is a release
   gate. It need not run in CI on every push or pull request.
3. Record how this newly requested disposable-test approach updates
   [ADR-010's earlier single-environment lab policy](../architecture/decisions/ADR-010-single-environment-lab.md)
   before provisioning a new environment. The policy rejected a standing extra
   test platform; the proposed environment is disposable and run-scoped.
4. Define ownership and retention for installation artifacts, protected test
   credentials, run reports, and any databases retained after test cleanup.

Related procedures: [fresh deployment and acceptance](../operators/validation/acceptance.md),
[human access validation](../operators/validation/access-and-authorization.md),
and the [playbook component matrix](../operators/validation/playbook-component-matrix.md).
