# Platform API guide

Status: current. Last reviewed October 9, 2026.

The REST API is the authoritative boundary used by the UI, CLI, CI, and test
automation. Its machine-readable contract is [OpenAPI](../api/openapi.json); this
page explains behavior that is easy to miss when reading individual operations.

## Access and resources

Use a bearer token issued by the configured OIDC provider. The API validates the
issuer, signature, audience, and lifetime, then evaluates platform-owned grants.
Human and machine identities use the same authorization boundary but have
different credential lifecycles.

The main resources are projects, declarations and revisions, durable operations,
grants, deployment credentials, diagnostics, and bounded operator surfaces.
Project routes are scoped by the project name; access to one project does not
grant access to another.

## Writes and concurrency

An application deployment is a complete desired-state `PUT`, not a patch. Use
`If-Match` with the last observed revision on updates. A stale revision returns
`409 revision_conflict`; fetch current state, merge deliberately, and retry.

Accepted work returns an operation ID. Poll its status URL until the operation is
terminal and inspect its separate readiness snapshot. `succeeded` means resources
were applied. Only a ready snapshot establishes workload readiness.

## Error model

- `401`: missing, invalid, or expired authentication.
- `403`: authenticated but not authorized for the action and resource.
- `404`: the resource does not exist or is not visible to the caller.
- `409`: state or revision conflict.
- `422 invalid_spec`: malformed or inconsistent declaration.
- `422 unsupported_capability`: valid request not supported by this environment.
- `503`: a required platform dependency is unavailable.

Retry dependency failures with the same desired state after investigating the
dependency. Do not retry authorization or validation failures unchanged.

## Contracts and diagnostics

Use the [application declaration reference](application-spec.md) for field-level
semantics. Interactive documentation is available at `/docs` and the live schema
at `/openapi.json`. Diagnostic and operator endpoints remain authorization-scoped;
raw Kubernetes or Docker access is never part of the public application contract.
