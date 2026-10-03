# Security and Identity

Status: source implementation of the accepted ADR-004 identity and grant boundary; deployment and controlled lab acceptance remain open.

## Current security boundary

The API validates individual OIDC access tokens against a configured issuer, audience and JWKS endpoint, then resolves every request against platform-owned PostgreSQL grants keyed by immutable issuer/subject pairs. Keycloak is the supported lab reference provider, but the API does not depend on Keycloak-specific token claims or APIs. The one-time host-side bootstrap subject creates the first platform-admin grant; a shared `PLATFORM_TOKEN` is no longer accepted for project operations. Health/readiness, OpenAPI/docs and the certificate gate remain unauthenticated. Source also contains an append-only, redacted `platform_audit.events` boundary for mutations, denials and membership changes. Deployment and operational acceptance are unverified.

The provisioner connects as PostgreSQL `postgres`. Its Kubernetes ServiceAccount has cluster-wide get/list/create/patch/update permissions for the allowed resource kinds, including namespaces, Secrets and Deployments. RBAC does not restrict it to `project-*` names. It has no mounted Docker socket. Its only delete verb is on namespaces, for confirmed project retirement, and an admission policy limits that to managed `project-*` namespaces; it remains privileged infrastructure. The external controller uses a long-lived token Secret; bootstrap also enables Kubernetes Secret encryption. See [ADR-012](../03-decisions/ADR-012-admin-provisioning-baseline.md).

Each project gets one database-owning login and a password derived by HMAC-SHA256 from `DATABASE_KEY` and the project name. Runtime, migration and human identities are not separated. Existing SQL passwords are not updated on PUT, so changing the key alone produces incompatible workload credentials. [ADR-013](../03-decisions/ADR-013-database-credential-lifecycle.md) documents this recovery/rotation coupling.

Workload manifests enforce non-root/read-only execution, quotas and NetworkPolicies. All services and k3d nodes still share one Docker network; PostgreSQL transport TLS is absent, and new-pod egress can precede policy convergence. Loki has authentication disabled, and shared monitoring does not enforce project permissions. These are trusted-lab controls, not hostile-tenant isolation.

## Trust boundaries

Identity, platform permissions, and application business permissions remain separate. A central OIDC provider authenticates people and clients. The target Application Catalog owns organization/project/environment membership, ownership, and grant facts. The Catalog and Platform API each enforce those facts for their own endpoints; the Platform API also enforces deployment and infrastructure policy. Hosted applications decide their own business roles.

Catalog-to-control-plane calls use a service identity and return stable IDs plus versioned permission facts, not reusable user credentials. Accepted operations record the actor and authorization/catalog versions used. Long-running or destructive work revalidates authorization before a material change. Python workers receive only the approved operation and scoped provider credentials; they cannot grant access or broaden the plan.

Platform users do not automatically receive Kubernetes access. The provisioner uses separate infrastructure credentials with the smallest practical scope and operation set.

## Phase 1B role model

| Role | Read | Deployment/configuration | Operations | Grants / data deletion |
|---|---|---|---|---|
| viewer | Authorized status, redacted logs/metrics | No | No | No |
| developer | Yes | Authorized scopes, no privilege escalation | As explicitly permitted | No |
| project-admin | Yes | Yes | Yes | Project-scoped; separate confirmation for data deletion |
| platform-admin | All project scopes | Yes | Yes | All project grants; separate confirmation for data deletion |

Later phases may add operator or organization roles without weakening these permissions. Keycloak authenticates the principal, but platform-owned bindings authorize project access. Bindings use the immutable OIDC issuer/subject pair rather than mutable usernames or email addresses. The API reads grants on every request, so a revoked binding denies the next request. A platform role never grants hosted-application business-data access.

Database read/write permissions are separate grants and do not follow automatically from log/deployment permissions. Even an administrator does not automatically receive business-data access to a hosted application.

OIDC identities use stable issuer and subject identifiers, not only mutable display names. Validate token signatures, issuer, audience, and validity. Human CLI clients use Authorization Code with PKCE or Device Authorization; machine-to-machine flows use separate service identities and explicit grants. Frontends contain no client secrets. Keycloak is the supported lab reference deployment, while API authentication remains provider-neutral OIDC.

## Resources and secrets

Workloads, CI, and interactive database users receive separate identities. Database roles separate runtime DML from schema migration/ownership. Network access, authentication, and object authorization are distinct checks.

Secret values are excluded from Git, ApplicationSpec, audit events, and AI context. Authorized secret references are permitted in ApplicationSpec; they do not disclose stored values. Rotation proceeds from a new credential version through updated bindings and successful reconnection to revocation of the old version.

Docker daemon access belongs exclusively to the privileged provisioning path. A restricted API proxy alone does not guarantee tenant isolation: even permitted container creation must prevent arbitrary host mounts, privileged containers, and socket mounts. The lab assumes trusted workloads.

Kubernetes isolation requires RBAC, quotas, and enforced NetworkPolicies in addition to namespaces. Verify CNI/policy support and expose it as a capability.

## Audit and security assessments

Audit events include actor, scope, action, resource ID, revision, operation ID, timestamp, and result. Also record denied access and grant changes. Define tamper protection and retention operationally.

Proposed tools include Trivy for scanning and Kyverno for policies; runtime detection is a later option. Findings need severity, affected version, owner, deadline, and justified exceptions. Begin with visible findings, then add blocking rules after validation.

## AI access

AI receives only authorized, redacted data within the user's scope. Logs and documents are untrusted input and cannot change tool permissions. Write actions use an explicitly approved plan with a target and revision; approval does not replace authorization at execution time.

Core decision: [ADR-004](../03-decisions/ADR-004-identity-and-access-management.md). Incidents: [Runbook](../05-operations/runbook.md).
