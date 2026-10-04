# Phase 2B Automation Credential Implementation Plan

Status: **source implementation complete; deployed acceptance remains open**. This plan extends the Phase 2B deployment-credential work with an explicitly privileged test-runner identity and empty-project bootstrap. Phase 2A live acceptance remains deferred.

## Objective

Support two deliberately different automation paths:

- a project-scoped `deployment` credential that can deploy and observe exactly one project; and
- a platform-scoped `test-runner` credential, created by a human platform administrator, that can create disposable projects and short-lived test personas so the platform authorization and feature suite can run without reusable human tokens.

An empty project must be creatable before its first application deployment so a platform administrator can establish the scope, grant a project administrator, and issue a CI deployment credential before CI submits the first desired specification.

## Ordered implementation

1. Add `POST /projects` for an audited, platform-admin or test-runner-authorized empty project and represent that project with an explicit `empty` lifecycle state and no desired specification.
2. Audit every existing project consumer and give status, logs, revisions, rollback, restart, retirement, grants, and first deployment well-defined behavior for an empty project.
3. Generalize automation-credential metadata to distinguish `deployment`, `test-runner`, and `test-persona` identities while retaining provider references, expiry, use, rotation, revocation, creator, scope, and test-run ownership without storing secrets.
4. Add human-platform-admin-only create/list/rotate/revoke operations for the reusable test-runner credential. A machine identity must not be able to mint another test runner.
5. Add test-runner-authorized creation/list/revocation of temporary service-account test personas with `viewer`, `developer`, `project-admin`, or disposable `platform-admin` grants. Exercise the separate restricted `deployment` profile through the project credential endpoint.
6. Retain per-request platform-state authorization, immediate denial after expiry or revocation, one-time secret disclosure, bounded rotation overlap, provider cleanup retry, and fail-closed behavior for every credential profile.
7. Reuse the narrow Keycloak client adapter for service-account identities and the `platform-api` audience. Interactive human-login testing remains a separate browser-flow concern.
8. Split automation into a one-time test-runner bootstrap playbook and a repeatable basic platform suite. The repeatable suite obtains fresh bearer tokens, creates a unique empty project and personas, tests allowed and denied behavior, performs the first deployment with the deployment identity, exercises rotation/revocation, and cleans up in an `always` block.
9. Ensure all secret- or token-bearing Ansible tasks use `no_log`, all public/audit representations are redacted, and test reports contain only stable non-secret evidence.
10. Add unit/API coverage for empty projects, credential profiles, privilege boundaries, first CI deployment, rotation, expiry, revocation, cross-project denial, provider failure, and cleanup; then run the existing regression suite and syntax/configuration validation.
11. Reorganize fresh-deployment documentation around human bootstrap, test-runner configuration, basic platform tests, empty-project creation, and project CI credentials. Keep backup, recovery, watchdog, heartbeat, Alertmanager, and their tests in separate operational tracks.

## API outline

- `POST /projects` creates an empty project. `PUT /projects/{name}` remains the first and subsequent desired-state deployment operation.
- `/projects/{name}/deployment-credentials` manages narrowly scoped deployment identities.
- `/platform/test-runner-credentials` manages privileged reusable suite identities and accepts only a human platform administrator as actor.
- `/platform/test-identities` lets a test runner or human platform administrator create and clean up short-lived role personas tied to a test-run identifier.

## Acceptance outcome

A human platform administrator creates one expiring, revocable test-runner client and places its client ID and secret in protected suite configuration. Subsequent runs use no human token: they create an empty disposable project, create role personas, establish grants, deploy the first revision with a project deployment credential, prove the permission matrix and feature behavior, prove rotation/expiry/revocation denial, and remove their temporary identities and project resources. Operational backup and alerting acceptance remains separate.
