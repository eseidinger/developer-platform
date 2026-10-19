# Platform API guide

Status: current. Last reviewed October 18, 2026.

The REST API is the authoritative boundary used by the UI, CLI, CI, and test
automation. Its machine-readable contract is [OpenAPI](../api/openapi.json); this
page explains behavior that is easy to miss when reading individual operations.

## Access and resources

Use a bearer token issued by the configured OIDC provider. The API validates the
issuer, signature, audience, and lifetime, then evaluates platform-owned grants.
Human and machine identities use the same authorization boundary but have
different credential lifecycles.

The main resources are projects, declarations and revisions, durable operations,
grants, deployment credentials, named-store resources/bindings/leases, AI
runs/proposals, diagnostics, and bounded operator surfaces.
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

### Retained operational logs

`GET /projects/{name}/retained-logs` requires project `view` authority, like the
existing kubelet `/logs` endpoint. It reads minimized centralized events including
retired pod instances. Filters: `component`, `instance` (pod), `tail` (1–1000),
`since_seconds` (1–604800), `after` and `before` (timezone-aware ISO timestamp or
nanosecond cursor). `next_cursor` is a nanosecond timestamp; `after` excludes that
timestamp. Retrieve events sharing a timestamp together with a sufficient tail;
this is not lossless streaming. Historical component names remain queryable.
Arbitrary LogQL, backend URLs and raw payload search are not supported.

Responses distinguish `ok`, `no_output`, and `unavailable`; unavailable storage
never becomes empty success. Entries contain timestamp, pod/container/component,
validated revision/operation metadata and event/level/opaque correlation.
`retention.source=loki`, `seconds=604800` and `state=configured` describe
configuration, not a certified retention drill. Only the
[operational envelope](../../infrastructure/monitoring/README.md#central-workload-logs-and-correlation)
is centralized; ordinary application text remains kubelet best effort.
`GET /v1/capabilities` advertises these supported contracts in `observability`;
it does not attest collector health or elapsed retention in the current environment.

## Named data stores

Resources have an independent lifecycle under `POST/GET /v1/projects/{project}/resources`
and `/v1/resources/{resource_id}`. A resource-owning administrator grants human
access or approves a component binding. Cross-project binding requests remain
pending until owner approval. Only an active approved binding named in the
consuming `v1alpha2` component supplies a store Secret and private relay egress.
Unbound and legacy applications receive no implicit database.

Store mutations use JSON `version` fields, distinct from hosted-access ETags and
deployment revisions. Retirement retains data and revokes access; purge confirms
resource UUID, owner and version and waits for verified off-host backup intent.
Provider enablement and capacity come from operator settings. Neo4j Community
supports full-instance `read-write` access only, rejecting read-only grants.

Interactive humans inspect `/v1/store-access/me`, issue a 24-hour credential at
`POST /v1/store-access/{grant_id}/credentials`, and reveal only their active lease
at `/v1/store-access/credentials/{credential_id}`. Pending issuance returns 202;
inspect that lease/history before retrying an uncertain creation. Console launch
assertions are browser-only; raw provider endpoints remain private. See
[resource lifecycle](../operators/data-stores.md) and
[human connection instructions](database-access.md) for request bodies and provider limits.

The legacy `database-access` grant/password issuance POSTs return 410.
`data-services` summarizes visible named resources, component bindings and
current binding credential state. An empty project has no implicit database.
Use the named-resource and lease endpoints for detailed observations.

## AI assistance

Project-scoped `/projects/{name}/ai/` endpoints expose context, classification,
run history and rollback proposals. Human project viewers can create a run with
`{"kind":"explain_application"}`, `investigate_incident`, or
`development_assistance`. Runs require Public/Internal classification and a
configured eligible external provider. A human platform administrator changes the
separate AI policy using `{"classification":"internal"}`; changing general
project governance does not itself set the AI policy.

Runs execute synchronously within a 90-second budget and save durable results,
evidence, usage completeness and estimated cost. A disconnected request does not
cancel server work. History and detail reads mark records still running after ten
minutes as failed with a safe interruption explanation; they do not retry model
work. Inspect history before retrying an uncertain POST. Automation can read authorized
history but cannot start human assistance or approve writes.

A completed sourced incident investigation bound to the current revision can
create a proposal with `{"run_id":"RUN_UUID"}` when the latest apply failed or
a server-observed runtime failure is confirmed. The target is a retained successful
revision. Review its structural diff and exact `diff_sha256`; approval and execution
are separate JSON POSTs carrying that hash. Human management authority, current
revision and a single-use 15-minute approval are rechecked before the normal
rollback operation is accepted. No database rollback or arbitrary model write is
implemented. Poll the returned deployment operation and readiness separately.
See [UI assistance](ui.md#use-ai-assistance) and the
[AI telemetry reference](../../infrastructure/monitoring/AI.md).

## Hosted application access

Hosted access is separate from authorization to administer the Platform API.
`GET /v1/capabilities` advertises it in `hostedApplicationAccess`, including modes,
group authorization, identity transport, project-wide credential isolation and
the `v1alpha2` requirement. Public workload readiness does not authorize callers;
without an active access policy the public route denies access.
Project administrators manage application groups, access policies, first-login
requests, memberships, and provider-approved service-access requests under
`/v1/projects/{project}/`. There is no implicit application membership for a
platform or project administrator. The initial implementation supports a
`v1alpha2` application with one public component; its application name is the
project name in the default environment.

The portal's overview reads `GET /v1/projects/{project}/application-access-context`.
It returns the public component and URL, eligibility/reason, and server-derived
`manage` and `consume` permissions for that project. The companion
`GET /v1/projects/{project}/application-access-operations` returns at most 100
recent scoped operation summaries, including operations on incoming provider
service requests, with an authorized `canRetry` flag. Both endpoints require
project `view`, return no credentials, and set `Cache-Control: no-store`. A
retired or legacy/private-only project reports why access configuration is not
eligible; callers must still handle `403` and dependency failures distinctly.

Create a group with `POST /v1/projects/{project}/application-groups`, a JSON body
such as `{"name":"readers","displayName":"Readers"}`, and an
`Idempotency-Key`. The response contains its stable `grp_…` ID. Define the access
policy using `PUT /v1/projects/{project}/applications/{application}/access-policy`:

```json
{
  "component": "api",
  "defaultDecision": "deny",
  "identityAttributes": {"displayName": false, "email": false},
  "routes": [
    {
      "name": "interactive",
      "match": {"pathPrefix": "/app/", "methods": ["GET", "POST"]},
      "authentication": {"mode": "browser-session"},
      "authorization": {"anyOfGroups": ["readers"]}
    },
    {
      "name": "machine",
      "match": {"pathPrefix": "/api/", "methods": ["GET"]},
      "authentication": {"mode": "bearer-token"},
      "authorization": {"anyOfGroups": ["readers"]}
    }
  ]
}
```

Group names resolve to stable IDs at acceptance. Browser policies require a
`GET` entry route. Authentication protocol paths under `/oauth2` are reserved;
no application route is anonymous. Policy bodies do not contain an audience,
redirect URI, realm, OAuth scopes, or proxy flags.

Access-resource responses contain `id`, `kind`, `project`, `name`, `state`,
`version`, `spec`, `created_at`, and `updated_at`, plus a quoted version `ETag`.
Updates and transitions require that exact `If-Match`; stale versions return
`412`, and omitted optional update preconditions return `428`. Endpoints whose
header is required in OpenAPI return `422` when it is absent. Idempotent group
and service-request creates return the existing resource on replay and `409`
if a key is reused with different content. Asynchronous responses include
`operation_id` and `status_url`; poll `GET /v1/access-operations/{id}`. The
provider and consumer can inspect their shared service operation. Provider
failures retry durably; a permanently failed grant can be explicitly retried
using `POST /v1/access-operations/{id}/retry` with the resource's current
`If-Match` and renewed administrator authority.

Human first login creates a pending access request, not a membership. List
`application-access-requests` as the provider administrator, then `POST` its
`/{id}/approve` with `{"groups":["grp_…"]}` and `If-Match`. Grant projection
must finish before it is effective. Group assignment can be extended using
`/{id}/groups`; remove individual memberships using
`DELETE /v1/projects/{project}/application-group-memberships/{id}`. Rejected
human requests require administrator reopening. Accounts and initial passwords
remain the identity administrator's responsibility.

A consumer creates `POST /v1/projects/{consumer}/service-access-requests` with
an idempotency key and this intent:

```json
{
  "name": "provider-reader",
  "providerProject": "provider",
  "application": "provider",
  "projectWideCredential": true
}
```

Only the provider administrator approves it with allowed bearer-route groups
at `/v1/projects/{provider}/service-access-requests/{id}/approve`. Until approval
and reconciliation, no usable service credential exists. An active response
reports the derived `audience`, `providerUrl`, and `secretPrefix` in `spec`;
credentials themselves are never returned. The consumer's managed project
secret receives `<secretPrefix>_CLIENT_ID`, `_CLIENT_SECRET`, and `_TOKEN_URL`.
Every project component can receive them. Obtain a five-minute token using
`client_credentials`; declare public HTTPS egress to both the identity provider
and the provider application. The token is not a Platform API credential.

The consumer can `POST /{id}/rotate` with `{"emergency":false}`, wait for the
new credential, confirm application adoption with `POST /{id}/confirm`, and
thereby revoke the previous client. Normal overlap is at most 24 hours;
`{"emergency":true}` removes old-client authority without overlap. Either owner
can revoke service access via `DELETE` in its own project scope.

Record project classification and domain-retention ownership using
`PUT /v1/projects/{project}/governance`; see its exact fields in OpenAPI. Email
release requires `personalData:true` before policy acceptance. Applications
read the normalized headers described in the
[security architecture](../architecture/security-and-authorization.md#upstream-identity-transport);
they do not receive the bearer token or implement the platform group check.
