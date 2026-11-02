# Protected identity lookup for hosted applications

Status: planned specification. The API and lookup grant are not implemented.

## Purpose and scope

The Platform provides a protected, application-scoped API for selecting and
validating principals before a hosted application assigns its own permissions.
The contract applies to every eligible hosted application. The Platform owns
identity resolution and service-access status; the application owns its domain
permissions and stores assignments under opaque Platform principal IDs. Names
are used only for search and display.

This API does not create users, service access, application groups, or domain
assignments. It does not grant Platform or hosted-application permissions.

## Decisions

- The Platform selects the configured issuer and realm. Callers cannot submit
  either value.
- An exact `preferred_username` lookup covers all currently active users in the
  realm, including users who have not visited a hosted application. There is no
  prefix search or user enumeration endpoint.
- Each hosted application receives an explicit, revocable lookup permission
  scoped to its own application. A project `view` role or ordinary application
  group membership does not imply this permission.
- A service list contains only active service access approved for the caller's
  target application. Each item includes the consumer project, access name,
  target application, and principal ID.
- The application checks a selected principal again on its server immediately
  before persisting an assignment. A user must still have an active account; a
  service must still have active, approved access to that application.
- The application persists the principal ID, principal kind, and its own
  permission data. Display names are refreshed separately and never used as
  authorization keys.

## Authorization boundary

The API authenticates the calling backend with a Platform API credential and
checks its current, application-scoped lookup grant on every request. The grant
binds a caller identity to exactly one stable target application ID. The target
is derived from that grant, not from an untrusted request parameter. A Platform
administrator can grant or revoke this capability; granting it requires an
explicit administrative action and an audit record. The exact grant-management
endpoint and credential provisioning method must be defined alongside the API
implementation.

The Platform returns no identity-provider credentials, email addresses, token
claims, or service client secrets. Responses use `Cache-Control: no-store`.
Lookup attempts, denied calls, and grant changes are audited without storing
bearer tokens or unnecessary personal attributes. Rate limits apply per caller
to reduce username probing.

## Proposed HTTP contract

The following paths are proposed under the Platform API. They represent one
application context resolved from the caller's grant.

### Resolve a user

`POST /v1/application-identity/users/resolve`

Request: `{"preferredUsername":"alice"}`. The value must be nonempty and within
a documented length limit. Matching uses the identity provider's canonical rules
for `preferred_username`; the Platform must not silently choose among multiple
matching active accounts.

Success: `{"principalId":"prn_…","kind":"user","preferredUsername":"alice"}`.
The Platform reads the current realm account, requires it to be active, and
atomically creates or reuses the stable mapping from configured
`(issuer, subject)` to principal ID. The response may include the configured
issuer only if a consumer needs it for display; the caller never chooses it.

### List eligible services

`GET /v1/application-identity/services?cursor=…&limit=…`

Success returns a paginated `items` array. Each item has `principalId`,
`kind: "service"`, `consumerProject`, `accessName`, `targetApplication`, and
`serviceAccessId`. The target application is the caller's application. Results
are drawn from current Platform service-access resources and include only
`active` entries whose provider approval has not been withdrawn. `pending`,
`provisioning`, `revocation-pending`, `revoked`, and other non-active states are
ineligible. The endpoint exposes no credential material. Pagination has a
documented maximum page size and stable ordering.

### Validate a selected principal

`POST /v1/application-identity/principals/validate`

Request: `{"principalId":"prn_…","kind":"user"}` or
`{"principalId":"prn_…","kind":"service"}`.

Success: `{"principalId":"prn_…","kind":"…","assignable":true}`. For a user, the
Platform resolves the stored issuer and subject and confirms that the current
realm account exists and is active. For a service, it confirms that the
principal belongs to an active service-access resource whose target is the
caller's application. A service principal without an active matching resource is
not assignable. This check does not grant application access.

The application performs validation in the server-side assignment handler, after
authenticating and authorizing its operator and before its local write. Because
the Platform and application do not share a transaction, a successful check is a
point-in-time statement. The application must enforce its own permissions when
they are used; it cannot treat an old validation result as a permanent
service-access grant.

## Errors and availability

- `401`: missing or invalid caller credential.
- `403`: caller lacks the application-scoped lookup grant.
- `404`: no matching active user, unknown principal, or principal outside the
  caller's application scope. These cases use the same external response where
  necessary to avoid disclosing cross-application identities.
- `409`: exact username is ambiguous or conflicts with an existing principal
  mapping. No assignment may proceed.
- `422`: malformed request or unsupported principal kind.
- `429`: caller rate limit reached.
- `503`: identity provider or required Platform state is unavailable. The
  application must fail closed for new assignments and may retry later.

The API must not return `assignable: true` from a stale user-account cache or
from a service-access status that has already been revoked. Existing local
assignments are governed by the application's own lifecycle policy; this API
does not automatically delete them.

## Implementation fit and acceptance

The current Platform already maps `(issuer, subject)` to stable hosted-access
principal IDs and stores service-access resources and their states. Human
principals are currently created on first application contact, so complete realm
lookup and active-account validation require a read-only identity-provider
adapter. The adapter must resolve an exact login name and fetch an account by
subject, expose only required fields, and use credentials with the minimum
required realm-read permissions. Provider errors must remain distinct from
unknown users. Service eligibility must be computed from current Platform
resources rather than identity-provider client names.

Acceptance requires evidence that:

1. An active user without previous application login resolves to the same
   principal ID on repeated calls; disabled, absent, and ambiguous users cannot
   be assigned.
1. A caller can list and validate only active service access to its own target
   application; pending, revoked, and cross-application access is excluded.
1. Revoking the caller's lookup grant denies its next API call.
1. Revoking service access or disabling a user prevents the next server-side
   assignment check, including when a prior lookup succeeded.
1. Responses contain no secrets and use `no-store`; lookup and denial events are
   audited without sensitive claims.
1. Identity-provider outage prevents new user resolution and validation without
   producing a false `not found` result.
1. The principal-ID column is unique, and validation by ID cannot return an
   arbitrary identity if stored rows conflict.

## Required contract decisions before implementation

OpenAPI and implementation work must not start until the following decisions are
recorded in this specification and reflected in the API contract:

1. **Lookup grant and backend authentication:** Define the grant-management
   operation, the credential type and provisioning path, rotation and revocation
   behavior, and the binding between caller identity and stable application ID.
   An application name alone is insufficient as a binding key.
1. **Username semantics:** Confirm that `preferred_username` is the unique login
   identifier in the supported provider profile. Define case sensitivity,
   Unicode normalization, exact-match behavior, and the result when an account
   is renamed. A renamed account must retain its principal ID because the
   mapping is keyed by issuer and subject.
1. **Principal-ID uniqueness:** Add a database uniqueness constraint on
   `hosted_access_principals.id` and a migration that checks existing rows for
   duplicates before applying it. Define how validation handles a detected
   integrity conflict; it must fail closed.
1. **Service eligibility and pagination:** Specify the exact service-resource
   states and approval evidence required for eligibility. Define the cursor
   encoding, maximum page size, stable sort key, and whether pages represent a
   snapshot or may reflect changes between requests. Callers must revalidate a
   selected service before assignment regardless of pagination semantics.
1. **Identity-provider adapter:** Define the read-only lookup-by-name and
   lookup-by-subject operations, minimum provider permissions, timeouts, and
   distinction between absent accounts and provider failures.
