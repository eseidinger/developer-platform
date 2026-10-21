# Energy-System Use-Case Enablement Priority Plan

Status: priority Phase 3 delivery slice. Adopted October 10, 2026.

This plan makes the generic Developer Platform capabilities needed by the
[AI-assisted energy-system configuration scenario](https://github.com/eseidinger/energy-system-configuration)
the next delivery priority. It implements the Developer Platform work packages
`DP-01` through `DP-03` and supplies the platform evidence needed by integration
gates 4 and 5. The platform must not know about ODIP, VEF, datasets, simulations,
or optimization runs. Their declarations, domain identities, fine-grained
business authorization,
publication behavior, energy adapter, simulation and optimization, and AI user
journey remain owned by their respective projects and the cross-project suite.

Execution tracking is in the
[phase task index](../backlog.md#phase-task-index). Complete this slice before
starting new Phase 3 breadth beyond work already in progress.

## Outcome

Allow separately owned consumer and provider applications to run on the
Developer Platform and communicate over an authenticated, encrypted,
least-privilege connection. Applications can retain state across restart and
recovery, expose meaningful health and diagnostics, and produce enough generic
deployment and correlation evidence for an external cross-project acceptance
suite. The energy-system projects exercise these contracts without receiving
product-specific platform behavior.

The first release uses public HTTPS for application-to-application connectivity:

```text
User -> consumer application public HTTPS
                    |
                    | provider audience token + HTTPS
                    v
               provider application public HTTPS
```

Private cross-project routing is not part of this slice. Activating it requires
a separate capability contract and acceptance suite; Kubernetes service
reachability or an ad hoc NetworkPolicy change is not a platform contract.

## Ownership boundary

The Developer Platform owns reusable contracts and mechanisms only: the
application-declaration schema, hosted-application identity, managed secret
delivery, public routing, explicit egress, persistence, health discovery,
diagnostics, backup, and recovery. Platform source, fixtures, APIs,
configuration, and operational runbooks must use domain-neutral concepts and
must not branch on application or project names.

The application repositories own their `v1alpha2` declarations and images,
application-access-policy intent, group vocabulary, service-access targets,
health semantics, correlation values, any fine-grained domain authorization,
data classification, and deterministic domain checks.
The cross-project repository owns the energy-system end-to-end workflow and may
use ODIP and VEF names. Its results are evidence that the generic platform
contracts support the use case, not a reason to add product-specific platform
profiles or behavior.

## Priority order

### 1. Freeze generic capability decisions and application-owned inputs

Record the following before implementation-dependent acceptance begins:

- Public HTTPS is the initial cross-project route. The generic contract covers
  DNS, TLS termination, platform-derived token audience, normalized identity
  context, credential provisioning, and rotation.
- Support independently owned projects composed of one public component,
  private workers and optional scheduled components, each with its own retained
  PostgreSQL database. Do not encode a named application's topology as a
  platform profile.
- Require public OCI images pinned by digest for the first release. Private image
  support is a separate platform capability.
- Advertise PostgreSQL as the durable application-state capability in this
  increment. If an application requires a filesystem, PVC, or object store, stop
  and add that generic durable-storage capability before accepting its deployment.
- The encrypted-channel rule covers cross-project public HTTPS, not
  application-to-PostgreSQL traffic. PostgreSQL TLS is not required in this
  first-release lab profile, and evidence must not imply that all application
  traffic is encrypted.
- The project is the service-credential isolation boundary; every component may
  receive a credential delivered through the project secret mechanism.
- Apply the retention and Public, Internal, Confidential, and Restricted
  classification rules accepted in
  [ADR-020](../../../architecture/decisions/ADR-020-generic-hosted-application-integration.md).
  Application owners supply classification and domain-row retention as project
  governance metadata; the platform owns infrastructure retention.

Application-owned deployment declarations must use `platform.example/v1alpha2`,
custom HTTP readiness paths for public APIs, bounded resources, and explicit
outbound access. A worker that needs semantic readiness exposes a private health
port rather than being treated as healthy merely because its process is running.
Platform-owned fixtures use neutral provider/consumer names and validate the
same schema without copying declarations from a product repository.

#### Confirmed application inputs

The application owner confirmed on October 11, 2026 that:

- the applications fit the platform's current advertised resource and execution
  limits, so this use case does not require a new quota, scaling, or long-running
  execution capability;
- PostgreSQL is the only durable-storage capability they require, so PVC,
  filesystem, and object-storage support do not block the use case; and
- the projects can supply the required classification and domain-retention
  governance records under the ADR-020 model.

These confirmations close the corresponding capability questions. They do not
replace validation of the concrete declarations, onboarding records, or the
deployed resource and retention behavior in the external acceptance suite.

### 2. Deliver hosted-application identity

Source implementation progress (October 11, 2026): the generic access-resource
API, authoritative PostgreSQL catalog and durable reconciliation, human approval,
provider-approved machine credentials, immutable policy revisions, normalized
headers, private backend policies, replicated authorizer, per-application proxy,
rotation, revocation, and recovery quarantine are implemented. Local regression,
isolated PostgreSQL lifecycle, real Keycloak PKCE/client-credentials, and pinned
proxy configuration tests establish source-level behavior. Subsequent deployed
core evidence is recorded below; the energy configuration contract remains
untouched.

Implement and verify the platform first; reconcile application-owned declarations
and the external configuration contract against the resulting API afterward.
Source/local evidence does not close PLAN-009. The neutral-fixture DNS/TLS,
private-backend isolation, expiry and healthy-system revocation checks have now
passed in [EV-45](../backlog.md#verification-register); dependency-outage and
restored-access drills remain required. Component monitoring and immediate
central log ingestion now have deployed evidence in EV-46 below; elapsed
workload-log retention and the external energy end-to-end gate remain open. Operational
setup is in the [hosted-access runbook](../../../operators/identity-and-access.md#hosted-application-access-installation-and-recovery).

Acceptance automation progress (October 11, 2026): the neutral
`scripts/tests/platform/check-hosted-access.py` harness now provides an offline plan, explicitly
confirmed live core checks, optional held-token expiry and isolated recovery
reconciliation, safe private evidence, and resumable scope-checked cleanup.
Provider/consumer fixtures use one public component and a private worker, only
synthetic PostgreSQL state, and no domain-specific application authorization.
The fixture image and local regression/persistence checks pass. The external
configuration contract remains unchanged. Follow the
[harness procedure](../../../operators/validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness)
for repeatable digest-pinned deployed checks.
Reports distinguish core success from deferred checks; reconciliation is not a
real backup restore. PLAN-009/PLAN-018/PLAN-019 remain open.

Deployed core acceptance (October 11, 2026): the operator-provided node-01 report
for run `c927adee1d50` records `core-passed`, all 39 named assertions passed,
held-token expiry enabled, and `completed-data-retained` cleanup. Runner/fixture
release `hosted-access-v0.1.2` identifies source `e8f74fd`; the report separately
pins the harness hash and image digest but does not identify the deployed
control-plane source revision. Public HTTPS managed service access, project-wide
worker binding, human approval, group enforcement, IPv4 backend/egress isolation
with positive controls, PostgreSQL isolation and restart read-back, policy
activation/rollback, rotation, expiry and existing-session/token revocation have
deployed evidence. See [EV-45](../backlog.md#verification-register) and the
[detailed run record](../../../operators/validation/access-and-authorization.md#executed-hosted-access-core-acceptance-october-11-2026).
This is core capability evidence, not an external energy-workflow result or full
gate closure (`gateClosed: false`). Backup restore, long browser/rotation timers,
request retention, component monitoring/central log retention, control-plane
outage, DNS-change/reapply, recovery reconciliation and the external suite remain
deferred. Keep those tasks open; reconcile the external contract against the
implemented API without adding energy-specific platform behavior.

Deployed monitoring acceptance (October 11, 2026; EV-46): operator-provided
node-01 run `60c3ca1647b9` passed all 45 core-plus-monitoring checks after the
collector state-permission fix and confirmed healthy Alloy startup. Both public
API component probes, independent Kubernetes readiness and project-authorized
central correlation/revision/operation reads passed. Runner/fixture release
`hosted-access-v0.2.0` supplies the pinned image; the subsequent collector fix
does not need another fixture image. The report does not attest the exact
deployed control-plane tree. Cleanup completed with data retained. See the
[detailed EV-46 run record](../../../operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026).
The combined monitoring/retention deferral remains: post-retirement/restart log
readback and seven-day retention/compactor deletion still need evidence.
`gateClosed: false`, the other deferred checks and the external suite remain
unchanged; this is no energy-domain acceptance or PLAN-017 completion.

Implement [PLAN-009](../backlog.md#additional-phase-tasks) before the deployed
connection gate. The capability must support these reusable registration types:

- an `ApplicationAccessPolicy` with explicit, non-overlapping route/method rules,
  an authentication mode, and allowed application-group IDs;
- project-scoped `ApplicationGroup` resources and audited memberships;
- a `browser-session` mode for interactive authentication;
- a `bearer-token` mode and distinct confidential service identity for machine
  access;
- platform-derived browser redirect URIs, clients, machine audiences, and
  minimal standard OIDC scopes and client-scoped group claims;
- first-login human access requests with no default membership;
- provider-approved machine service-access requests with group assignment before
  credential activation;
- delivery of a service credential to its owning project without exposing it in
  desired state, logs, audit exports, or ordinary reads;
- explicit acknowledgement that every component in the project may receive the
  credential;
- rotation, revocation, retirement cleanup, and recovery coverage; and
- proof that platform roles and deployment credentials grant no application
  group implicitly.

The public contract consists of application groups, route access policies,
human access requests/approvals, and machine service-access requests/approvals.
Applications select modes, routes, and groups, not OIDC protocol values. It must
not expose Keycloak- or OAuth2-Proxy-specific configuration. The supported lab
uses one Keycloak realm per platform environment with distinct application
clients and audiences. It maps stable platform group IDs to
application-resource-client roles and emits relevant roles in a client-scoped
`groups` claim. Each public application receives a platform-managed OAuth2 Proxy
configuration for browser OIDC. A shared replicated platform authorizer handles
automatic first-login registration, route-specific authorization, revocation
overrides, machine-token validation, and normalized headers. Route traffic
through that boundary and keep the application backend private so another
workload cannot bypass authentication or forge identity/group headers.

The initial modes are deliberately distinct:

- `browser-session` redirects an unauthenticated browser, stores authentication
  in a secure HTTP-only cookie, and applies CSRF protection to state-changing
  requests;
- `bearer-token` accepts no browser session, never redirects, and returns `401`
  for a missing, invalid, expired, or wrong-audience access token; and
- both supply the same normalized principal/group context and return `403` when
  that verified principal lacks a group allowed by the matched rule.

A public component may bind the modes and different group sets to exact paths or
segment-aware prefixes with explicit methods. Query parameters do not
participate, `HEAD` follows `GET`, and `OPTIONS` requires an explicit rule.
Reject invalid/ambiguous path encoding and dot segments. Each externally
reachable application route must match exactly one rule; reject overlaps and
deny unmatched routes. Authorization uses non-empty `anyOfGroups` only. The
initial profile supports neither anonymous routes nor a general
`session-or-bearer` route.

The following YAML shows the conceptual provider-neutral resource shape. The
implemented REST API accepts the JSON specification directly at the
project/application-scoped endpoint, not this illustrative Kubernetes-style
envelope; see the [API guide](../../../developers/api.md#hosted-application-access).
The initial resource shape is:

```yaml
apiVersion: platform.example/v1alpha1
kind: ApplicationGroup
metadata:
  project: provider
  name: application-administrators
spec:
  displayName: Application administrators
status:
  id: grp_7ae814
  state: active
---
apiVersion: platform.example/v1alpha1
kind: ApplicationAccessPolicy
metadata:
  project: provider
  name: public-access
spec:
  component: public-api
  defaultDecision: deny
  identityAttributes:
    displayName: true
    email: false
  routes:
    - name: browser-application
      match:
        pathPrefix: /app/
        methods: [GET, POST, PUT, PATCH, DELETE]
      authentication:
        mode: browser-session
      authorization:
        anyOfGroups: [application-users, application-administrators]
    - name: browser-administration
      match:
        pathPrefix: /admin/
        methods: [GET, POST, PUT, PATCH, DELETE]
      authentication:
        mode: browser-session
      authorization:
        anyOfGroups: [application-administrators]
    - name: machine-read
      match:
        pathPrefix: /machine-api/
        methods: [GET]
      authentication:
        mode: bearer-token
      authorization:
        anyOfGroups: [machine-readers, machine-writers]
    - name: machine-write
      match:
        pathPrefix: /machine-api/
        methods: [POST, PUT, PATCH, DELETE]
      authentication:
        mode: bearer-token
      authorization:
        anyOfGroups: [machine-writers]
```

Names are convenient references within the project; the generated group ID is
the stable authorization value. The exact API envelope may be refined during
implementation, but it must preserve these semantics and must not expose the
identity provider's realm, client, group-path, or proxy configuration.

Groups, policies, human requests, memberships, service requests, and approvals
are first-class Platform API resources separate from deployment declarations.
Use generated stable IDs, `If-Match`/resource versions, idempotent creates,
audited transitions, and the existing durable-operation mechanism for provider
reconciliation. The initial states are:

| Resource | States |
| --- | --- |
| Human access request | `pending`, `approved`, `rejected`, `cancelled`, `expired` |
| Membership | `provisioning`, `active`, `revocation-pending`, `revoked`, `failed` |
| Service access | `pending`, `approved`, `provisioning`, `active`, `rejected`, `cancelled`, `failed` |

The initial API surface follows the existing project/application hierarchy:

```text
POST /v1/projects/{project}/application-groups
PUT  /v1/projects/{project}/applications/{application}/access-policy
GET  /v1/projects/{project}/application-access-requests?state=pending
POST /v1/projects/{project}/application-access-requests/{id}/approve
POST /v1/projects/{project}/application-access-requests/{id}/reject
DELETE /v1/projects/{project}/application-group-memberships/{id}
POST /v1/projects/{consumer}/service-access-requests
POST /v1/projects/{provider}/service-access-requests/{id}/approve
POST /v1/projects/{provider}/service-access-requests/{id}/reject
```

The implemented response envelope and operation polling are specified in
[OpenAPI](../../../api/openapi.json) and the
[API guide](../../../developers/api.md#hosted-application-access). Access resources
have stable IDs, quoted version ETags, and status URLs; clients do not submit
Keycloak resource identifiers or receive credential values.

PostgreSQL is authoritative. A grant becomes effective only after Keycloak
provisioning succeeds. A revocation becomes locally ineffective immediately,
stays `revocation-pending` while Keycloak cleanup retries, and never regains
access because cleanup failed. A group with active policy or membership
references cannot be deleted. Project retirement revokes memberships and
clients before provider cleanup.

Access policies use immutable revisions and atomic activation. Load a complete
validated revision into every ready authorizer replica; remove a replica that
cannot load it from readiness. Restrictive changes deny first and permissive
changes grant last. Retain the prior revision for bounded rollback and never
evaluate a request against a mixture of revisions.

The stable identity and group headers are always present on admitted requests.
`identityAttributes.displayName` explicitly opts into the display-name header.
Email requires a separate explicit opt-in and a project classification record
covering personal data. Optional attributes may be absent and are never
authorization keys.

#### Human creation and authorization flow

1. Create or federate the human account in the configured identity provider;
   identity administration owns passwords, MFA, recovery, invitations, and
   self-registration. Project administrators cannot create realm users.
2. Let the provider owner create project-scoped application groups and an access
   policy containing a `browser-session` route. Derive the client and callback
   URI from the component's platform-owned public hostname.
3. Complete Authorization Code with PKCE at the authentication proxy and create
   a secure browser session. Map the verified `(issuer, subject)` to a stable
   platform principal ID.
4. On first login, automatically create or reuse the pending
   `ApplicationAccessRequest` keyed by application, issuer, and subject, with no
   group. Return a platform pending page or a safe `403` response with code
   `application_access_pending`; do not forward the request to the application.
5. Let a provider project administrator review the request and assign one or
   more application groups. Being a project administrator authorizes this
   control-plane action but does not automatically assign an application group.
6. Reconcile the membership into the identity provider's client-scoped claim.
   After session/token refresh, apply the route policy and forward the normalized
   user and group context only when an allowed group matches.

The prioritized applications use this first-login flow. Designating an
application administrator means assigning that approved identity to the
application-administrator group; it does not require application-local user or
role administration for coarse route access.

Pending requests expire after 30 days and a later login may create a new one.
Rejected requests do not reopen automatically; a project administrator must
reopen them. Remove terminal request and revoked-membership records after 90
days while retaining minimized lifecycle audit events under the audit policy.
The `project-admin` platform role is the initial access-management authority;
application-administrator membership grants application route access only.

The pending request and approval are represented without copying mutable profile
attributes into authorization keys:

```yaml
apiVersion: platform.example/v1alpha1
kind: ApplicationAccessRequest
metadata:
  project: provider
  name: request-93fb6d66
spec:
  application: provider-application
  principal:
    kind: user
    issuer: https://identity.example.org/realms/platform
    subject: 2dbb64ce-2fd4-4a85-b371-51b8c4657e21
status:
  state: pending
---
apiVersion: platform.example/v1alpha1
kind: ApplicationAccessApproval
metadata:
  project: provider
  name: approval-93fb6d66
spec:
  requestRef: request-93fb6d66
  groups: [application-users, application-administrators]
```

Approval creates durable, separately revocable membership records. Subsequent
group changes operate on these records rather than changing the historical
approval:

```yaml
apiVersion: platform.example/v1alpha1
kind: ApplicationGroupMembership
metadata:
  project: provider
  name: prn-93fb6d66-application-administrators
spec:
  principalRef: prn_93fb6d66
  groupRef: grp_7ae814
status:
  state: active
```

#### Machine creation and authorization flow

1. Let the consumer owner submit a service-access request referencing the
   provider's `bearer-token` access policy.
2. Let a provider project administrator approve the request and assign the
   provider's machine groups before issuing a usable credential.
3. Derive the audience from the target's stable platform identifier, create the
   service principal and confidential client, reconcile the selected groups, and
   deliver the secret once through the consumer project's managed secret path.
   Record that any component in that project may use it, so the identity does not
   provide component-level attribution.
4. Let the consumer obtain a short-lived token with `client_credentials`.
5. At the provider boundary, validate signature, issuer, access-token type,
   audience, expiry and other validity times, subject, client identifier, and
   relevant group claim. Apply the matched route's group policy before forwarding
   a normalized `service` context.

The consumer request contains no self-authorizing group assignment. The provider
approval supplies it:

```yaml
apiVersion: platform.example/v1alpha1
kind: ServiceAccessRequest
metadata:
  project: consumer
  name: provider-access
spec:
  target:
    project: provider
    accessPolicy: public-access
  reason: Read and update provider resources
---
apiVersion: platform.example/v1alpha1
kind: ServiceAccessApproval
metadata:
  project: provider
  name: consumer-provider-access
spec:
  requestRef:
    project: consumer
    name: provider-access
  groups: [machine-readers, machine-writers]
```

The common identity context contains an opaque stable principal ID, principal
kind, issuer, subject, relevant stable group IDs, and validated client ID where
applicable. Email, username, display name, group display name, and secret value
are never stable authorization keys. A valid session or target-audience token
authenticates a principal but does not admit a protected route without a matching
group. Application-defined OAuth scopes are not part of the initial profile.

The authentication boundary transports that context on every authenticated
request using the reserved `X-Platform-Principal-Id`,
`X-Platform-Principal-Kind`, `X-Platform-Principal-Issuer`,
`X-Platform-Principal-Subject`, and, for service principals,
`X-Platform-Principal-Client-Id` headers, plus
`X-Platform-Principal-Group-Ids` for both kinds. Applications read the headers
into a request-local security context and do not parse platform cookies or
bearer tokens. The optional name header requires access-policy opt-in; email also
requires classified personal-data handling. Both are display attributes only.
The platform has already enforced coarse route authorization; the application
adds authorization only for finer object or domain decisions that the route
policy cannot express.

PLAN-009 acceptance must prove:

- successful login and stable user identification after mutable display
  attributes change;
- creation of a pending first-login request, denial before approval, and access
  after a provider project administrator assigns an allowed group;
- no automatic application group for a platform or project administrator;
- denial of a machine before approval and successful client-credentials access
  only after provider approval and machine-group assignment;
- `401` for a missing, invalid, expired, or wrong-audience token and `403` for a
  valid principal lacking a group allowed by the matched route;
- browser redirect, secure-cookie, logout, session-expiry, and CSRF behavior;
- explicit path/method separation and default denial when both authentication
  modes share a public component, including rejection of overlapping rules and
  no ambiguous credential precedence;
- exact and segment-aware prefix behavior, `HEAD`/`OPTIONS` handling, rejection
  of ambiguous path encoding, non-empty `anyOfGroups`, and denial of anonymous
  or unmatched application routes;
- client-scoped group claims that do not disclose unrelated project membership;
- denial of forged identity/group headers and direct backend access around the
  access boundary;
- consistent normalized identity and group headers for both modes, rejection of
  missing or malformed required headers, and removal of the original bearer
  token;
- no application access derived from platform administrator, project, or
  deployment roles;
- audited group and membership lifecycle, and membership revocation within the
  accepted claim/session staleness bound;
- fail-closed authorizer snapshot expiry, prompt revocation override, five-minute
  token/claim refresh, and the accepted browser idle/absolute lifetime;
- atomic policy revision activation, deny-first restriction, grant-last
  permission, replica-readiness behavior, and rollback;
- normal replacement-client rotation with confirmation and 24-hour maximum
  overlap plus emergency no-overlap rotation;
- display-name and classified-email opt-in without authorization dependence;
- request expiry/reopening/pruning, rotation, revocation, retirement cleanup,
  redaction, backup, and outward-only recovery of principals, groups,
  memberships, policies, and identity bindings; and
- a recreated human or service identity receives none of the earlier identity's
  memberships.

The external energy-system suite requests instances of these generic bindings
and validates its human and service-principal group policies. The platform must
not define energy-domain roles, resource permissions, or product-specific group
profiles. Any dataset-, object-, or row-level rule remains external application
behavior.

The accepted maximum delay between authoritative membership revocation and
enforcement is five minutes. Each replicated authorizer uses a versioned
policy/membership snapshot for no more than five minutes and consumes prompt
invalidations. It may serve existing traffic during a control-plane outage only
while authentication material and that snapshot remain valid, then fails
closed. `revocation-pending` is a platform-side denial override even when a
stale token or session contains the group.

Machine access tokens last at most five minutes and receive no refresh token.
Browser authorization claims refresh at least every five minutes; browser
sessions use a 30-minute idle timeout and eight-hour absolute lifetime. Logout
clears the application cookie and initiates provider logout where supported.

Normal machine credential rotation creates a replacement client for the same
logical service principal and a new managed-secret version. The old and new
clients overlap for at most 24 hours while the consumer confirms adoption; the
old client is then revoked, or automatically revoked with an adoption-timeout
condition. The logical principal ID remains stable and the client-ID header
identifies the version. Emergency rotation has no overlap.

Recovery treats the restored platform catalog as authoritative and reconciles
outward to Keycloak. Protected routes remain unavailable until clients, roles,
mappers, memberships, and authorizer policy reconcile. Invalidate browser
sessions; preserve pending/rejected states; reprovision active memberships; keep
`revocation-pending` denied; and rotate any service credential whose restored
client and managed secret cannot be proven consistent.

An explicitly accepted operator-managed client-provisioning runbook may unblock
the first demonstration, but it does not complete PLAN-009 or establish a
self-service platform capability.

### 3. Correct component monitoring and correlation

Source implementation (October 11, 2026): PLAN-017 now derives public component
targets/declared paths, preserves legacy probes and omits private-only projects.
Protected probes check the access boundary without credentials; Kubernetes
readiness supplies semantic workload health. Dedicated read-only Kubernetes log
collection sends minimized operational envelopes to seven-day configured Loki.
Derived revision/operation annotations become non-indexed metadata, while opaque
application correlation remains domain-neutral. Authorized retained-log reads
enforce fixed project selectors and safe response envelopes. Local container
fixtures and regressions verify source behavior; `--monitoring` adds deployed
neutral checks. See the
[implemented contract](../../../../infrastructure/monitoring/README.md).
EV-46 now establishes deployed neutral provider/consumer boundary probes,
semantic readiness and immediate central correlation reads after the collector
permission/readiness repair. PLAN-017 remains open for post-retirement/restart
log readback and elapsed seven-day retention/compactor acceptance; EV-45 remains
historical and is not retroactively promoted.

Monitoring discovery must understand the component application schema. For each
declared public component, publish the actual
`<component>-<project>.<apps-domain>` target and component health profile. Do not
publish a legacy project hostname for a component application or publish a
blackbox target for an application without public exposure.

Add legacy and `v1alpha2` regression tests, project/component labels, and a
deployed probe check using neutral fixtures. Define a generic correlation
envelope for application-supplied correlation keys plus deployment revision and
platform operation ID. The external suite decides which domain identifiers it
supplies. Bearer tokens, customer details, secret values, and raw correlation
values classified as sensitive must not appear in platform logs or explanations.

Use the authorized project log, component status, resource, and operation APIs as
the minimum demonstration evidence. Select and implement central Kubernetes
workload-log retention if the kubelet's best-effort window cannot meet the
retention decision from step 1.

### 4. Prove the authenticated deployed connection

Create a platform-owned automated acceptance playbook using neutral provider and
consumer fixtures that:

1. deploys digest-pinned multi-component provider and consumer projects;
2. waits for application readiness and verifies their separate databases;
3. provisions and activates a consumer-to-provider credential through the
   platform secret mechanism;
4. applies the provider public route and component-scoped consumer DNS/443
   egress rule;
5. authenticates a human through the browser boundary, observes a pending
   first-login request, and proves denial until a provider project administrator
   assigns an allowed application group;
6. verifies DNS, certificate validation, pre-authorized service-principal
   identity, platform-derived token audience, client-scoped group claim, and
   route-policy authorization;
7. proves denial for an unauthenticated identity, forged identity or group
   headers, a direct backend request, a wrong audience, a valid but unapproved or
   wrong-group principal, and an unrelated egress destination; and
8. captures image digests, application revisions, routes, component status,
   resource bounds, and correlation-safe logs.

DNS-based egress is resolved to fixed IP rules at deployment time. The playbook
must show the approved resolved addresses and prove that a changed destination
requires an explicit reapply rather than silently widening access.

Separately, the externally owned energy-system suite deploys its
application-owned declarations and proves dataset and other business-level
authorization beyond the generic route/group boundary. The platform records
that suite's versioned result as use-case evidence but does not duplicate its
applications or assertions in platform source.

### 5. Prove durability and recovery

Extend the generic platform workflow to restart the neutral applications and
verify retained database state and version isolation. Extend the external
cross-project workflow to reproduce its completed domain result and verify that
an older result remains pinned after corrected source data is introduced.

Take a verified platform backup and restore it through the supported isolated
recovery workflow. The platform-owned test proves restoration of generic
application resources, database state, principals, groups, memberships, access
policies, routes, and identity-provider bindings. The external suite reapplies
its project declarations, reactivates required identity material, and reproduces
its reference result. Together, record the snapshot, image and contract
versions, recovery duration, restored database checks, route/TLS result, and any
manual identity steps. Byte-level backup readback or a generic SQL marker alone
does not satisfy the combined acceptance check.

## Exit criteria

This priority slice is complete only when:

- `DP-01`: independently owned applications are ready after restart with isolated
  retained databases, immutable images, managed secrets, readiness, and bounded
  resources, demonstrated generically by the platform and concretely by the
  external suite;
- `DP-02`: an authenticated application-to-application request succeeds over
  verified HTTPS and an unrelated destination is denied;
- `DP-03`: application identity and the selected public routing boundary are
  documented as explicit capabilities with isolation tests;
- component-aware monitoring observes the actual declared public endpoints
  without application-specific discovery logic;
- the Gate 4 platform playbook and Gate 5 cross-project suite pass in one
  environment; and
- recovery reproduces the recorded reference result from restored state.

Do not claim completion from local application tests, independently healthy
deployments, source inspection, generic platform recovery evidence alone, or an
external scenario that depends on unrecorded product-specific platform changes.

## Follow-on work, not a blocker

- Private cross-project service bindings and paired namespace policies.
- Component-specific configuration and secret bindings.
- Private registry credentials.
- PVC or object-storage resources.
- General OpenTelemetry/trace storage beyond the accepted correlation evidence.

Foundations:
[Application declaration](../../../developers/application-spec.md),
[application contract](../../../architecture/application-contract.md),
[security boundary](../../../architecture/security-and-authorization.md),
[observability](../../../architecture/observability.md), and
[backup and recovery](../../../operators/backup-and-recovery.md).
