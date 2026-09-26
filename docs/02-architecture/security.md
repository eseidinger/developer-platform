# Security and Identity

Status: security design draft. Keycloak is proposed, not confirmed as installed.

## Trust boundaries

Identity, platform permissions, and application business permissions remain separate. A central OIDC provider authenticates people and clients. The Platform API decides permissions within Organization → Project → Environment → Resource scopes. Hosted applications decide their own business roles.

Platform users do not automatically receive Kubernetes access. The provisioner uses separate infrastructure credentials with the smallest practical scope and operation set.

## Initial role model

| Role | Read | Deployment/configuration | Operations | Grants / data deletion |
|---|---|---|---|---|
| viewer | Authorized status, redacted logs/metrics | No | No | No |
| developer | Yes | Authorized scopes, no privilege escalation | As explicitly permitted | No |
| operator | Yes | Operational changes | Restart, scale, rollback within scope | No |
| project-admin | Yes | Yes | Yes | Project-scoped; separate confirmation for data deletion |
| organization-owner | Organization administration | Through explicit bindings | Through explicit bindings | Memberships and projects |

Database read/write permissions are separate grants and do not follow automatically from log/deployment permissions. Even an administrator does not automatically receive business-data access to a hosted application.

OIDC identities use stable issuer and subject identifiers, not only mutable display names. Validate token signatures, issuer, audience, and validity. Browser/CLI and machine-to-machine flows use suitable separate clients. Frontends contain no client secrets.

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
