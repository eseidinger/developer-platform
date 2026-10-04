# Phase 2B – CI Deployment Credentials

Status: **in implementation by owner direction; Phase 2A live acceptance is deferred, not accepted.** Covers [F-14 and F-15](../01-product/requirements.md), [UC-08 and UC-09](../01-product/use-cases.md), and [ADR-018](../03-decisions/ADR-018-revocable-ci-deployment-credentials.md). The executable breakdown is preserved in the [automation implementation plan](phase-2b-automation-implementation-plan.md).

Execution tracking: [DEV-012-T01 through DEV-012-T03](delivery-backlog.md#phase-task-index).

## Goal

Allow a CI pipeline to deploy and observe an application through a dedicated machine identity whose credential is narrowly scoped, expiring, rotatable, auditable, and immediately revocable without affecting a developer's interactive access.

## Credential contract

The public resource is a `deployment credential`, not a provider-specific client. It contains:

- stable credential ID and human-readable name;
- project and environment scope, with an optional application restriction;
- the fixed initial `deploy` action set;
- active, expired, `revocation_pending`, or revoked status;
- creation time, expiry, rotation relationship, and last-used time; and
- the immutable OIDC issuer/subject identity associated with the platform grant, kept out of ordinary developer responses where it is not needed.

Creation returns secret material exactly once. The initial Keycloak-backed profile returns an OIDC client ID and client secret suitable only for the client-credentials flow. Later reads never return the secret. The platform does not accept that client secret directly as an API bearer key; CI exchanges it for a short-lived access token with audience `platform-api`.

The `deploy` action set allows the scoped machine identity to read the target application and capabilities, submit or update its desired revision, and read the resulting operation, deployment status, and redacted diagnostics needed to decide whether the deployment succeeded. It excludes credential/grant administration, secret-value reads, project or application retirement, data deletion, operator APIs, and all other projects.

Only a project administrator within the scope or a platform administrator may create, rotate, list, or revoke deployment credentials. The platform checks the machine identity's grant on every API request. Revocation or expiry disables that grant first, so access is denied immediately even when an already issued OIDC access token has not expired.

The separate `test-runner` credential is a platform-scoped acceptance identity created, listed, rotated, and revoked only by a human platform administrator. It may create empty disposable projects and temporary service-account personas carrying ordinary platform grants, but it cannot mint another test runner. An empty project has no desired revision; it can receive grants and deployment credentials before CI performs its first `PUT /projects/{name}` deployment.

## Lifecycle and failure behavior

1. Create the platform credential record and provider client through one durable, resumable operation. Do not return a usable secret until both sides are durable.
2. Store only provider references and non-secret metadata in platform state. Secret material is returned once and must be stored by the CI system.
3. Rotate by creating a replacement credential linked to the predecessor. Permit a policy-bounded overlap, then revoke the predecessor explicitly or at its rotation deadline.
4. Revoke the platform grant before provider cleanup. If the provider is unavailable, report `revocation_pending`, keep API access denied, and retry cleanup idempotently.
5. Reconcile provider and platform records without silently recreating a revoked credential. Include credential metadata and authorization facts in backup/recovery scope. Client secrets remain only in protected identity-provider state and its encrypted recovery material; backup inventories, platform metadata exports, and restore logs never disclose them.

Audit creation, rotation, token-authenticated deployment actions, expiry, denial, and revocation with the credential ID, actor or machine principal, target scope, operation/revision, result, and timestamp. Never record the client secret, bearer token, authorization header, or complete sensitive provider response.

## Ordered implementation work

1. Finalize the API schema, expiry/overlap policy, provider-adapter contract, permission matrix, storage model, and redaction rules.
2. Implement authorized create/list/rotate/revoke operations, the Keycloak service-identity adapter, immediate platform-grant revocation, provider-cleanup reconciliation, and audit/backup coverage.
3. Add a CI example and run the acceptance scenario below. Only after this gate passes does Phase 2C resume.

## Acceptance scenario

Using a disposable project and repository pipeline:

1. a project administrator creates a project-scoped deployment credential and sees its secret once;
2. the pipeline obtains a short-lived OIDC access token without interactive login, submits an application revision, and follows the operation to a healthy observed result;
3. the deployment audit identifies the machine credential and revision without containing credential or token material;
4. cross-project access, credential/grant administration, secret-value access, retirement, data deletion, and operator endpoints are denied;
5. rotation permits the replacement credential to deploy during a bounded overlap, after which the old credential is denied;
6. explicit revocation denies the next request made with a still-unexpired access token;
7. expiry denies access without operator cleanup; and
8. identity-provider failure during create/revoke produces a visible, retryable, fail-closed state with no orphan that retains Platform API access.

## Out of scope for this gate

- CI vendor-specific integrations, hosted runners, webhook processing, and pipeline authoring beyond one portable example;
- general-purpose personal access tokens or direct long-lived bearer API keys;
- registry push credentials, source-control deploy keys, cloud-provider credentials, and workload identity federation;
- granting CI project administration, retirement, data deletion, or secret-value read access; and
- automatic credential issuance from untrusted pull requests.
