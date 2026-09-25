# ADR-004 – Central Identity, Separate Authorization

Created: September 25, 2026. Status: **Proposed**.

## Context

The platform, applications, CI, and database access need identities. Sharing a login does not imply sharing permissions. A platform administrator must not automatically receive business permissions in every hosted application.

## Proposed decision

Use OIDC as the identity boundary, with Keycloak as the initial implementation candidate. A shared realm is the proposed starting point; clients remain separate per application or technical purpose.

The platform stores memberships and role bindings scoped to projects/environments. Hosted applications use platform identity and their own business authorization by default. Platform-managed application roles and external application identity providers remain later modes.

People, CI, and workloads have separate principals. Infrastructure access goes through the provisioner, not automatically through human Kubernetes accounts.

## Alternatives

Representing every permission as an identity-provider role couples the platform domain to identity administration. A realm per project can provide stronger administrative separation but increases effort. Application-owned identity is flexible but complicates consistent self-service.

## Consequences

The API must check every access and background job within the correct scope. Specs can request permissions but cannot authorize themselves. Automatic client provisioning requires controlled redirect URIs, secret rotation, and cleanup.

## Validation

Incorrect audience, foreign project access, revoked membership, and unauthorized grant changes must fail. Application roles must not create platform permissions, or vice versa.

Details: [Security](../02-architecture/security.md), [Phase 3](../04-development/phase-3-developer-experience.md).
