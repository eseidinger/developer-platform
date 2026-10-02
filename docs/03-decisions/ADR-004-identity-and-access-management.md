# ADR-004 – Central Identity, Separate Authorization

Created: September 25, 2026. Accepted: October 2, 2026. Status: **Accepted; source implementation exists, deployment acceptance pending**.

## Context

The platform, applications, CI, and database access need identities. Sharing a login does not imply sharing permissions. A platform administrator must not automatically receive business permissions in every hosted application.

## Decision

Use standards-based OIDC as the platform identity boundary. Platform APIs depend on a generic OIDC contract; Keycloak is the supported reference deployment for the existing lab. The reference deployment uses one shared realm, with separate clients for each application or technical purpose. This selects Keycloak for the supported profile without coupling public API contracts or authorization data to Keycloak-specific APIs.

OIDC proves principal identity. Platform-owned data remains authoritative for authorization: the platform stores project/environment memberships and role bindings instead of encoding them as identity-provider realm roles. During Phase 1B the existing platform service owns these facts in its PostgreSQL state. Phase 2 migrates them to the Application Catalog through a reconciled, single-writer cutover that preserves principal and scope associations.

Identify a principal by the stable OIDC issuer and subject pair. Usernames, email addresses and display names are attributes, not authorization keys. Each API validates token signature, issuer, audience and validity before consulting the authoritative platform grant on every request. Removing a grant must therefore deny the next request; project permission is not retained merely because an access token remains valid.

Phase 1B uses this minimum role model:

| Role | Read authorized project state | Change deployments/configuration | Retire a project | Manage project grants |
|---|---:|---:|---:|---:|
| `viewer` | Yes | No | No | No |
| `developer` | Yes | Yes | No | No |
| `project-admin` | Yes | Yes | Yes | Within the project |
| `platform-admin` | All projects | Yes | Yes | All projects |

Destructive data deletion remains a separately authorized and confirmed operation. A platform role never grants access to hosted-application business data. Later phases may add operator or organization roles without weakening the Phase 1B permissions.

Human CLI clients use Authorization Code with PKCE or Device Authorization; they do not collect user passwords. Automation uses separately registered service identities and explicit platform grants. People, CI and workloads remain distinct principals. Infrastructure access goes through the provisioner, not automatically through human Kubernetes accounts.

The legacy shared `PLATFORM_TOKEN` is not accepted for ordinary developer project operations after the Phase 1B cutover. Any temporary bootstrap or break-glass path is operator-only, disabled by default after bootstrap, secret-protected and audited; it is never a developer fallback.

Hosted applications use OIDC authentication and their own business authorization by default. Automated hosted-application client provisioning, redirect-URI management, portal login, human database identity and additional organization experience remain Phase 3 work.

## Alternatives

Requiring Keycloak-specific APIs in platform contracts would make replacing the reference provider unnecessarily difficult. A platform-local username/password or token system would duplicate identity security and lifecycle responsibilities. Representing every permission as an identity-provider role would couple the platform domain to realm administration and complicate the planned catalog migration. A realm per project can provide stronger administrative separation but adds client, user and operational lifecycle overhead that the shared lab does not need.

## Consequences

The API must check every access and background job within the correct scope. Specs can request permissions but cannot authorize themselves. Authorization state, identity-provider configuration and required recovery secrets join backup and recovery scope. Audit records correlate the issuer/subject principal, scope, action and result without storing bearer tokens or unnecessary identity claims.

The Python baseline needs an OIDC adapter and platform-owned grant repository before expanded self-service. Phase 1C must reapply this boundary to each new endpoint and data surface. Phase 2 must preserve authorization behavior and audit correlation while grant ownership moves to the Application Catalog. Automatic hosted-application client provisioning requires controlled redirect URIs, secret rotation and cleanup in Phase 3.

## Validation

Reject invalid signature, issuer, audience and expired/not-yet-valid tokens. Prove foreign-project access and unauthorized grant changes fail. Revoke a membership and prove the next request is denied and audited even when the previously issued access token has not expired. Verify collection results include only authorized projects and apply the same checks to logs, metrics, secrets and jobs as those surfaces are introduced.

Prove `viewer` cannot mutate, `developer` cannot retire projects or manage grants, `project-admin` cannot cross project boundaries, and only `platform-admin` can administer all project grants. Verify application roles cannot create platform permissions, platform roles do not grant hosted-application business access, service identities cannot impersonate people, and no audit or export contains a bearer token or secret claim.

Source now contains the provider-neutral JWT verifier, platform-owned grant tables and checks, Keycloak 26.4.1 reference Compose profile, one-time bootstrap grant, and redacted audit hooks. Record the exact deployed provider version, realm/client configuration, redirect URIs, key-rotation behavior, backup coverage and controlled lab acceptance evidence before closing Phase 1B. This source update does not complete OPS-001, OPS-002 or OPS-004.

Details: [Security](../02-architecture/security.md), [Phase 3](../04-development/phase-3-developer-experience.md).
