# ADR-020 – Generic Hosted-Application Integration Boundary

Created and accepted: October 11, 2026. Status: **Accepted for the Phase 3
use-case enablement increment; implementation and operational acceptance remain
open**.

## Context

The prioritized cross-project use case requires independently owned applications
to communicate with authenticated HTTPS, retain state, expose diagnostics, and
recover without product-specific platform behavior. The platform needs a bounded
first-release contract for public topology, database transport, service-secret
scope, retention, and data classification before hosted-application identity and
deployed acceptance can proceed.

The platform remains unaware of application names and business concepts.
Application repositories own their declarations, images, data semantics,
fine-grained domain authorization, and row-level retention. The platform owns
generic authentication and coarse route authorization through project-scoped
application groups; the same contract applies to every hosted application.

## Decision

### Application and network boundary

Each project may expose one public component. Applications that need multiple
HTTP surfaces place them behind that component or route between their own
same-project components. Multiple public components are outside the initial
contract.

Cross-project application traffic uses public HTTPS. The calling component
declares the provider DNS name and TCP port 443 as explicit outbound access. DNS
destinations resolve to fixed policy addresses when a deployment is applied; an
address change requires an explicit reapply.

The encrypted-channel requirement covers cross-project application traffic. It
does not cover application-to-PostgreSQL traffic in the first release.
PostgreSQL TLS remains unconfigured and is an accepted single-host lab
limitation. Documentation and acceptance evidence must not claim that all
application traffic is encrypted.

### Identity and credential boundary

Hosted-application identity is a separate platform resource, not part of an
application deployment declaration. Application owners declare authentication
and authorization intent through an `ApplicationAccessPolicy`. Each protected
route on the one public component selects one of two initial authentication
modes, `browser-session` or `bearer-token`, and one or more allowed
project-scoped application groups. Applications do not supply OIDC client IDs,
redirect URIs, audiences, scopes, session settings, identity-provider group
paths, or proxy flags in the standard profile.

The reference deployment uses one identity realm per platform environment. It
does not create an application-specific realm. The platform creates separate
OAuth clients and audiences for each application or technical purpose and
creates application groups inside a project/application scope. Group resources
have opaque stable platform IDs; their human-readable names are mutable
attributes and are not authorization keys. In the Keycloak reference profile,
an application group is represented as an application-resource-client role
whose value is the stable group ID. A protocol mapper emits those roles in a
client-scoped `groups` claim. Tokens expose only group IDs relevant to their
target client and application, rather than all of a principal's platform
memberships. This mapping is an identity-provider adapter detail, not a public
contract.

The public platform contract exposes access policies, groups, memberships, and
service-access requests, not identity-provider configuration. For
`browser-session`, the platform generates the OIDC client and derives the
redirect URI from the platform-owned public hostname and callback path. It
selects minimal standard OIDC scopes, session policy, logout behavior, and proxy
configuration. For `bearer-token`, an authorized consumer references the target
access policy; the platform generates the confidential client, credential, and
target audience from stable platform identifiers. Application-defined OAuth
scopes are outside the initial profile; coarse authority is expressed with
application-group membership.

The contract does not expose Keycloak, OAuth2 Proxy, or proxy-specific flags.
The supported lab profile uses Keycloak as the OIDC provider, one
platform-managed OAuth2 Proxy deployment/configuration per public application,
and a shared replicated platform authorizer. OAuth2 Proxy owns that
application's browser client, cookie, callback, and OIDC exchange; it reads the
client-scoped `groups` claim and forwards verified claims only to the authorizer.
The authorizer validates machine bearer tokens, records first-login requests,
matches route policy, applies the platform revocation view, and emits normalized
upstream headers. Browser traffic passes through both components; machine
traffic bypasses browser-session handling but still passes through the
authorizer. A conforming replacement may change products while preserving this
separation and the public security behavior.

#### Human enrollment and authorization

A human account is created in, or federated into, the configured identity
provider by identity administration. The Developer Platform does not manage
realm passwords, MFA, recovery, invitations, or self-registration, and a project
administrator cannot create a realm user. On first access to a
`browser-session` route, Authorization Code with PKCE verifies the person and
creates a secure browser session. The authorizer maps the stable OIDC
`(issuer, subject)` pair to an opaque platform principal and automatically
creates or reuses one pending request keyed by application, issuer, and subject.
First login does not assign a group and does not admit the request to the
application. A browser receives a platform-owned pending page; an API-style
request receives a safe `403 application_access_pending` problem containing the
request ID. Neither response reaches the application backend.

A provider project administrator reviews the pending request through the
platform control plane and assigns one or more application groups, such as
`application-users` or `application-administrators`. The platform reconciles
the membership to the identity-provider representation used for the client's
group claim. On the next token or session refresh, the access layer checks the
stable group IDs against the route policy. A matching membership admits the
request; an authenticated principal without one receives `403`. A project
administrator may assign the application-administrator group to themselves or
another person, but the platform project role does not confer that application
group automatically.

#### Machine authorization

A consumer project requests access to a target `bearer-token` policy. A provider
project administrator approves the request and selects the target application's
machine groups, for example `machine-readers` or `machine-writers`, before the
credential becomes usable. The platform then creates the service principal and
confidential client, reconciles its approved groups, derives the audience, and
delivers the credential once to the consumer project's managed secret path.

The caller obtains a short-lived access token with `client_credentials`. The
provider boundary validates token signature, issuer, type, derived audience,
validity period, subject, client identifier, and relevant group claims. A
missing or invalid token returns `401` without a browser redirect. A valid token
without a group accepted by the route policy returns `403`. The Keycloak adapter
assigns the same application-client roles used for humans to the service-account
identity and emits the stable platform group IDs in the normalized claim and
header contract.

Both paths expose the same normalized identity context: an opaque stable
principal ID mapped to issuer and subject, principal kind (`user` or `service`),
stable application-group IDs, and, where applicable, validated client ID.
Email, username, display name, group display name, and credential value are
attributes, never stable authorization keys. The stable identity fields and
group IDs are always available after authorization. Display name is released
only when the access policy explicitly opts in; email additionally requires an
explicit opt-in covered by the project's personal-data classification record.
Optional attributes may be absent and must not affect authorization. Deleted
and recreated identities receive a new mapping and do not inherit earlier
memberships.

The access boundary supplies this context on each admitted upstream request
through the reserved `X-Platform-Principal-*` headers defined by the security
architecture, including `X-Platform-Principal-Group-Ids`. The application does
not parse the session cookie, receive the bearer token, or query the identity
provider to determine the current caller. Because the platform has already
enforced coarse route authorization, an application with no object- or
row-specific rules needs no additional authorization code. Applications remain
responsible for any finer domain decision that cannot be represented safely as
a route-and-method group policy.

A public component may use different modes on explicit, non-overlapping exact
path or segment-aware path-prefix and HTTP-method matches. Query parameters do
not participate. Methods are normalized and explicit; `HEAD` follows `GET`, and
`OPTIONS` is denied unless explicitly configured. Invalid percent encoding,
encoded slash or backslash, backslashes, and dot segments are rejected before
forwarding. Every externally reachable application route matches exactly one
policy rule; overlapping rules are rejected and unmatched routes are denied.
Each rule uses non-empty `anyOfGroups`; group inheritance, negation,
`allOfGroups`, general Boolean expressions, anonymous routes, and a general
`session-or-bearer` mode are outside the initial profile. Browser-session routes
redirect an unauthenticated browser and enforce CSRF protection. Bearer-token
routes never redirect, use no session cookie, and return `401` for missing or
invalid tokens. Both return `403` when a verified principal lacks an allowed
group. Platform-reserved login callback paths and private readiness endpoints
are not application policy routes.

The access boundary removes caller-supplied identity and group headers before
adding its own. The application backend is private and accepts ingress only
through that boundary; otherwise an in-project caller could bypass the policy
and forge headers. Each protected surface has exactly one authoritative identity
source and fails closed if authentication, group-policy evaluation, or
normalized header construction is unavailable. Group-definition, membership,
approval, denial, and revocation changes are audited without recording tokens or
secrets.

Application-group revocation has a maximum authorization-staleness bound of five
minutes. PostgreSQL holds desired membership state and Keycloak is a reconciled
projection. A grant stays non-authorizing while `provisioning` and becomes
`active` only after provider confirmation. Revocation immediately enters
`revocation-pending` and is removed from the authorizer's effective policy even
if an existing token or session still asserts the group; provider cleanup then
retries durably until `revoked`. A failed cleanup never restores access.

Each replicated authorizer keeps a versioned authorization snapshot for at most
five minutes and consumes prompt invalidations. It may continue existing traffic
during a control-plane outage only while authentication material and the
snapshot remain valid; after snapshot expiry it fails closed. Machine token
lifetime and browser claim refresh are at most five minutes. Browser sessions
have a 30-minute idle timeout and an eight-hour absolute lifetime, using an
application-specific Secure, HTTP-only, SameSite-protected cookie.

#### Control-plane resources and administration

Groups, access policies, human access requests, memberships, service-access
requests, and approvals are first-class Platform API resources separate from the
application deployment declaration. Stable IDs are platform-generated, updates
use resource versions/`If-Match`, repeated creates support idempotency, and
provider reconciliation uses durable operations. Ordinary reads contain no
token or client-secret value.

The initial lifecycle vocabulary is:

| Resource | States |
| --- | --- |
| Human access request | `pending`, `approved`, `rejected`, `cancelled`, `expired` |
| Membership | `provisioning`, `active`, `revocation-pending`, `revoked`, `failed` |
| Service access | `pending`, `approved`, `provisioning`, `active`, `rejected`, `cancelled`, `failed` |

Approval creates separately revocable membership records rather than mutating
historical requests. A group cannot be deleted while an active policy or
membership references it. Policy removal denies its routes before provider
cleanup. Project retirement revokes memberships and clients before removing
identity-provider configuration.

The existing platform `project-admin` role is the bootstrap and administration
authority for application groups, policies, approvals, and memberships. An
`application-administrators` group protects application administrator routes but
does not grant Platform API authority. A project administrator receives no
application membership implicitly and may explicitly assign one to themselves.
A platform administrator may recover project administration without thereby
receiving application access. A separate delegated application-access platform
role is outside the initial profile.

Pending human requests expire after 30 days. A later login may create a new
request after expiry. Rejected requests do not reopen automatically; a project
administrator must reopen them. Terminal requests and revoked membership records
are retained for 90 days, while safe audit events follow the append-only audit
policy and omit unnecessary profile attributes.

#### Policy and credential lifecycle

Access policies use immutable revisions. The platform validates and compiles a
complete revision, stages it on every ready authorizer replica, removes replicas
that cannot load it from readiness, and atomically activates one revision.
Restrictive changes deny in the authorizer before routing/provider cleanup;
permissive changes prepare dependencies and activate authorization last. A
request is evaluated against one complete revision, never a mixture. The prior
revision remains available for bounded rollback.

The initial policy language supports only non-empty `anyOfGroups`. Every public
application route is authenticated; `authentication: none` is not supported.
Public-component status means network reachability, not anonymous access.

Machine credential rotation creates a replacement client for the same logical
service principal, copies only already approved groups, and publishes a new
managed-secret version. Both clients may overlap for at most 24 hours while the
consumer confirms adoption; the old client is then revoked and its secret
removed. Lack of confirmation triggers automatic old-client revocation and an
adoption-timeout condition. `X-Platform-Principal-Id` remains stable while
`X-Platform-Principal-Client-Id` identifies the credential version. Emergency
rotation revokes the old client without overlap and accepts interruption.

#### Recovery

The restored platform catalog is authoritative and reconciles outward to
Keycloak; identity-provider state is never imported or bidirectionally merged as
authorization truth. Protected routes remain unavailable until the catalog,
authorizer policy, clients, roles/mappers, and memberships reconcile. Restored
browser sessions are invalidated. Pending and rejected requests retain their
state, active memberships are reprovisioned, and `revocation-pending` remains
denied. A service credential is retained only when its Keycloak client and
managed secret are restored consistently; otherwise it is rotated and
redelivered through the controlled secret path. Recovery status and evidence
contain counts and identifiers, never secret values.

The project is the first-release service-credential isolation boundary. A
service credential delivered through the project secret mechanism may be
visible to every component in that project. Application owners must not assume
component-level secret isolation or attribution. A request made with that
credential identifies the project service client, not the individual component
that used it. Component-scoped secret bindings or workload identity require a
separate generic capability and are not part of this increment.

Secret values are write-only through ordinary platform APIs, excluded from
desired state and ordinary reads, and redacted from logs, metrics, audit details,
plans, and acceptance evidence.

### Retention

| Data | Accepted first-release policy |
| --- | --- |
| Application database rows | The application owner defines and enforces domain-row retention while the project is active. |
| Project database after workload retirement | Retained until an explicitly authorized project purge. Retirement alone does not delete it. |
| Verified backups | Keep the latest verified snapshot plus 14 daily, 8 weekly, and 6 monthly recovery points. Deleted live data may remain recoverable until containing snapshots expire. |
| Workload logs | Seven-day centralized retention target. PLAN-017 must implement Kubernetes workload collection; kubelet best effort does not satisfy the target. |
| Metrics | Seven days or 4 GB, whichever limit is reached first. Metrics contain no Confidential or Restricted values. |
| Application revisions and operations | Keep the latest 25 revisions, plus protected revisions referenced by active operations or the last successful restart. Finished operations may be pruned with their revision; the audit record retains safe history. |
| Application access requests | Pending requests expire after 30 days. Remove terminal request records 90 days after approval, rejection, cancellation, or expiry; rejected requests require explicit reopening before then. |
| Application memberships | Retain active membership records. Remove revoked records after 90 days; retain their safe lifecycle audit events. |
| Audit events | Append-only with no automatic expiry in the lab. Review storage growth at least annually before introducing an owner-approved pruning or archive policy. |
| Revoked credentials | Remove usable live secret material through the credential lifecycle; retain only non-secret lifecycle and audit metadata. Backup copies expire under backup retention. |
| Acceptance evidence | Retain with the corresponding platform release and include only sanitized Public or Internal metadata. |

The platform owns whole-database, backup, log, metric, revision, audit, credential,
and release-evidence retention. Applications own domain-record retention inside
their database. A future purge workflow must remove the live project database,
live credentials, and applicable platform state without rewriting existing
verified backups.

### Data classification

| Classification | Examples | Required handling |
| --- | --- | --- |
| Public | Published documentation and public image references | May be publicly exposed through a separately declared capability; classification alone never makes an application route anonymous. |
| Internal | Project names, topology, image digests, revisions, operation IDs, health, and resource data | Expose only through authenticated platform or operator surfaces unless separately published. |
| Confidential | Customer or personal data, domain identifiers, database contents, and business results | Restrict to authorized project access, include only in encrypted backups, and minimize or redact from telemetry. |
| Restricted | Passwords, tokens, client secrets, private keys, database credentials, and backup credentials | Use managed secret mechanisms only; never place in desired state, ordinary reads, logs, metrics, audit details, explanations, or acceptance evidence. |

The first-release platform accepts ordinary application data up to Confidential
in PostgreSQL. Restricted data is limited to managed credential and secret
mechanisms. General Restricted business data requires a separate review and is
not accepted by default while PostgreSQL transport is unencrypted and host/root
operators remain a trusted boundary.

Domain identifiers default to Confidential unless an application owner records
a lower classification. Metrics contain only Public or Internal data. Logs may
contain Internal operational data and explicitly approved Confidential
correlation values, but no customer payloads or Restricted values. Normal structured
Quarkus/Spring message retention was enabled at the owner’s request on October 19,
2026; messages remain subject to those classification limits. The collector drops
unknown JSON fields and applies best-effort credential-pattern redaction. This
does not authorize arbitrary customer payloads or make redaction exhaustive.

Classification is project governance metadata, separate from the deployment
declaration so a deployment cannot lower its own handling requirements. Project
onboarding records the maximum stored-data classification, maximum telemetry
classification, presence of customer or personal data, domain-retention owner
and policy, purge authority, and recovery owner. Automation of that record is
future generic platform work; the first release requires it in acceptance
evidence.

### Prioritized-use-case fit confirmation

On October 11, 2026, the application owner confirmed that the prioritized
applications fit the current advertised resource and execution limits, require
no durable-storage capability beyond PostgreSQL, and can supply the required
project classification and domain-retention governance records. No new platform
capability is required for those three concerns. The external suite must still
validate the concrete declarations and records; this confirmation is not
deployed acceptance evidence.

## Consequences

The existing one-public-component schema remains sufficient and needs no
product-specific extension. Public HTTPS, explicit DNS/443 egress, separate
project databases, project-wide secrets, and generic group-protected routes
compose the initial connectivity profile. Hosted-application authentication and
coarse authorization remain PLAN-009 work, component monitoring and central
workload-log retention remain PLAN-017 work, and the deployed generic connection
gate remains PLAN-018 work.

The chosen topology adds one managed OAuth2 Proxy configuration/deployment per
public application and makes the replicated authorizer a protected request-path
dependency. Its readiness, policy-snapshot freshness, latency, and denial
metrics therefore join platform operational acceptance. The five-minute cached
snapshot permits only bounded control-plane interruption and never permits stale
authorization indefinitely.

Accepting unencrypted PostgreSQL transport and project-wide secret visibility is
a bounded lab choice, not a general production guarantee. An application that
requires database TLS, multiple public components, component-scoped secrets, or
general Restricted business-data handling requests a new generic capability;
the platform must reject or defer that requirement rather than add an
application-specific exception.

## Validation

Use neutral provider and consumer fixtures. Verify that the provider has one
public component, the consumer has component-scoped DNS/443 egress, both use
separate retained databases, and all project components receive the same project
secret without its value appearing in desired state or read surfaces. Verify
unsupported extra public components and undeclared connectivity fail.

PLAN-017 must demonstrate seven-day centralized workload-log retention and the
classification boundary. PLAN-018 must demonstrate authenticated HTTPS,
wrong-audience denial, unrelated-destination denial, and sanitized evidence.
Identity acceptance must also prove that first login creates a pending human
request without access, machine credentials are unusable until provider
approval and group assignment, group-protected routes return `403` without a
matching membership, externally supplied identity/group headers are ignored,
the private backend cannot bypass the access boundary, and platform roles confer
no application group. It must demonstrate client-scoped group claims, separate
browser and machine route behavior, membership revocation and authorizer-cache
expiry within the accepted staleness bound, and audit of membership changes. It
must also test exact/segment-prefix normalization, method behavior, overlap and
anonymous/unmatched denial; automatic idempotent enrollment and request
retention; attribute opt-in; policy revision activation/rollback; browser
session limits; and normal/emergency client rotation. Recovery acceptance must
invalidate browser sessions, reconcile catalog state outward, rotate an
inconsistent service credential, and account for database, identity, group,
policy, secret, and backup-retention behavior without treating byte readback as
application-level recovery proof.

Details: [application contract](../application-contract.md),
[security and authorization](../security-and-authorization.md), and
[use-case enablement plan](../../maintainers/delivery/plans/energy-system-integration.md).
