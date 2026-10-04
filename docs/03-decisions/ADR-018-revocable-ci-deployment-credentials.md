# ADR-018 – Revocable CI Deployment Credentials

Created: October 4, 2026. Status: **Accepted requirement and Phase 2B placement; detailed implementation remains proposed**.

## Context

Continuous-integration pipelines must deploy applications without borrowing a person's interactive access token or retaining a shared administrator secret. A pipeline credential can leak through CI variables, build logs, forks, or third-party actions, so it needs narrow scope, an owner, an expiry, rotation, immediate revocation, and useful audit attribution.

[ADR-004](ADR-004-identity-and-access-management.md) already requires separate automation identities, provider-neutral OIDC authentication, and platform-owned grants. It rejects a second platform-local username/password or bearer-token system. The CI requirement must extend that boundary rather than reintroduce the retired shared `PLATFORM_TOKEN` pattern.

## Decision

Represent each CI access key as a dedicated machine identity plus a platform-owned deployment grant. The public platform API manages a provider-neutral `deployment credential` resource. The supported Keycloak adapter creates a confidential OIDC client/service identity and returns its client secret once. CI stores that secret in its protected secret store and exchanges it with the configured issuer using the OAuth 2.0 client-credentials flow for a short-lived `platform-api` access token.

The credential is scoped to one project and environment, optionally narrowed to one application. Its initial action set permits reading the scoped deployment state, submitting an application revision, and reading the resulting operation/status. It does not permit managing grants or credentials, reading secret values, retiring a project, deleting data, using operator endpoints, or impersonating a person.

Only a project administrator for that project or a platform administrator can create, rotate, or revoke the credential. Creation returns the client secret once; list and audit responses expose only a credential ID, display name, safe prefix/fingerprint, scope, status, creator, expiry, and usage timestamps. Secrets, bearer tokens, and complete client identifiers are never logged or placed in audit details.

Every credential has an expiry bounded by platform policy. Rotation creates a distinct secret and supports a bounded overlap so CI can switch safely. Revocation first disables the platform grant, making the next Platform API request fail even if a previously issued access token remains cryptographically valid; identity-provider client cleanup follows as an idempotent operation and is retried if the provider is unavailable. Expiry follows the same fail-closed authorization path.

## Alternatives

A long-lived platform API key sent directly on every request would be simpler for clients, but it would duplicate identity validation and key lifecycle inside the platform and conflict with ADR-004. Reusing a developer's token would erase the human/machine boundary and make offboarding and audit attribution unsafe. A single CI credential shared by all projects would have excessive blast radius. Provider-specific Keycloak clients with no platform resource would be hard to discover, scope, audit, recover, and revoke consistently through the product API.

## Consequences

The platform needs a credential lifecycle API, a machine-principal/grant record, an OIDC administration adapter, idempotent create/rotate/revoke operations, and a recovery story for metadata and provider reconciliation. The public contract remains independent of Keycloak, while the reference deployment must grant only the minimum provider administration permissions needed for CI clients.

CI systems must protect the one-time secret, mask it in logs, avoid passing it in command-line arguments, and request a fresh short-lived access token for a job. The platform can attribute a deployment to a stable CI credential and its creator without treating the creator as the runtime actor.

If provider cleanup fails after platform revocation, API access remains denied and the credential is reported as `revocation_pending` until reconciliation succeeds. Creation fails closed: a secret is not reported as usable until both provider identity and platform grant are durable.

## Validation

Create a credential as a project administrator and prove its secret is returned once and is absent from ordinary list, status, audit, logs, and platform metadata exports. The identity provider's encrypted recovery material may contain its protected client state, but no backup inventory or restore log may disclose it. Use the credential in a non-interactive pipeline to obtain a short-lived token, deploy a revision, and follow the operation to its observed result.

Prove the credential cannot access another project, manage grants or credentials, read secret values, retire an application/project, delete data, or use operator endpoints. Revoke it and prove the next API request is denied while an earlier access token is still within its token lifetime. Rotate it with bounded overlap, move the pipeline to the replacement, revoke the old credential, and prove expiry is enforced. Exercise provider unavailability during creation and revocation and verify fail-closed behavior, visible retry state, and redacted audit correlation.

Details: [Phase 2B](../04-development/phase-2b-ci-deployment-credentials.md), [Security](../02-architecture/security.md), and [UC-08](../01-product/use-cases.md).
