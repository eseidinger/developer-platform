# Generic Use-Case Enablement Increment Plan

Status: active execution plan for `PLAN-016`. Contract decisions accepted
October 11, 2026 in
[ADR-020](../../../architecture/decisions/ADR-020-generic-hosted-application-integration.md).

This increment freezes the generic platform contract needed by the prioritized
energy-system use case and routes every implementation gap into a subsequent
task. It does not implement hosted-application OIDC or introduce
application-specific declarations, profiles, defaults, or behavior.

## 1. Establish the neutral reference scenario

Describe two anonymous projects:

- `provider`: public API, optional private worker, retained PostgreSQL.
- `consumer`: public entry point, optional private worker, retained PostgreSQL.
- Consumer calls provider through public HTTPS using a service identity.
- Consumer has outbound access only to the provider's DNS name on port 443.
- Both applications use digest-pinned images, bounded resources, readiness
  checks, configuration, and managed secrets.

This becomes the design fixture. It contains no energy-domain names, datasets,
or business rules.

## 2. Produce a fit-gap assessment

Validate the scenario against the current platform:

| Capability | Current state | PLAN-016 action |
| --- | --- | --- |
| Multi-component applications | Supported by `v1alpha2` | Confirm contract |
| Public component ingress | Supported, one public service per project | Accepted as sufficient for the first release |
| Private worker | Representable as a private service | Document pattern |
| Scheduled work | Supported | Confirm limits |
| Digest-pinned public images | Supported | Require for acceptance |
| Custom readiness | Supported | Require for public services |
| Resource and execution limits | Supported | Application owner confirms the use case fits the advertised limits; verify the declarations |
| DNS/443 egress | Supported and pinned at apply time | Document reapply semantics |
| Separate project databases | Supported | Confirm ownership and retention |
| Durable storage | PostgreSQL only | Application owner confirms no filesystem, PVC, or object store is required |
| PostgreSQL TLS | Not supported | Accepted outside the cross-project encrypted-channel requirement |
| Project secrets | Supported, but project-wide | Accepted as the first-release service-credential isolation boundary |
| Classification and domain retention | Governance record required | Application owner confirms the projects can supply the required records |
| Browser/service OIDC clients | Not implemented | Route to PLAN-009 |
| Component monitoring | Incorrect for `v1alpha2` | Route to PLAN-017 |
| Workload-log retention | Best effort | Implement the accepted seven-day centralized target in PLAN-017 |

The current schema and limits are documented in the
[application declaration reference](../../../developers/application-spec.md),
while its principles are in the
[application contract](../../../architecture/application-contract.md).

## 3. Accepted contract decisions

### Public topology

The initial contract permits one public component per project. An application
routes multiple HTTP surfaces behind that component or between its same-project
components. Multiple public components require a future generic capability.

### Database encryption

The encrypted-channel requirement covers cross-project public HTTPS only. It
does not include application-to-PostgreSQL traffic. PostgreSQL TLS remains
unconfigured as an accepted single-host lab limitation, and evidence must not
claim that all application traffic is encrypted.

### Secret scope

The project is the first-release service-credential isolation boundary. A
service credential may be visible to every component in the project.
Component-scoped secret bindings remain a future generic capability.

### Retention and classification

ADR-020 accepts the following retention boundary:

- Applications own domain-row retention while active.
- Project databases survive workload retirement until explicitly purged.
- Verified backups retain the latest plus 14 daily, 8 weekly, and 6 monthly
  recovery points.
- Central workload logs target seven days; PLAN-017 must replace kubelet
  best-effort retention with actual collection.
- Metrics retain seven days or 4 GB, application revisions retain the latest 25
  plus protected revisions, and lab audit events remain append-only without
  automatic expiry.
- Revoked credentials retain no usable live secret material; non-secret
  lifecycle metadata and backup copies follow their respective policies.

The accepted classification levels are Public, Internal, Confidential, and
Restricted. Ordinary application data up to Confidential may use PostgreSQL.
Restricted data is limited to managed credentials and secrets; general
Restricted business data is not accepted by default. Domain identifiers default
to Confidential. Metrics contain only Public or Internal data, while logs may
contain only approved Confidential correlation values and never customer
payloads or Restricted values.

Classification is project governance metadata rather than deployment state.
Project onboarding records maximum stored-data and telemetry classifications,
customer or personal data presence, domain-retention owner and policy, purge
authority, and recovery owner.

## 4. Record the architectural decision

ADR-020 records the generic hosted-application integration boundary covering:

- Public HTTPS as the initial cross-project boundary.
- Application-owned declarations and fine-grained domain authorization.
- Platform-owned authentication, first-login/pre-authorization lifecycle, and
  coarse route authorization through project-scoped application groups.
- Platform-derived browser redirects, OIDC clients, machine audiences, and
  client-scoped group claims from access policies and stable target references.
- Managed, write-only credential delivery.
- Explicit DNS/port egress.
- PostgreSQL and secret isolation decisions.
- Unsupported capabilities and rejection behavior.
- Backup/recovery ownership.
- The prohibition on application-name-specific platform behavior.

The decision index, application contract, security model, lifecycle, developer
reference, and product requirements link to the accepted decision.

## 5. Update the public contracts

Revise documentation to specify:

- How a public component's hostname is derived.
- How a consumer declares DNS/443 egress.
- DNS resolution and explicit reapplication behavior.
- The private-service pattern for workers.
- Readiness requirements.
- Resource and execution limits.
- Persistence and deletion behavior.
- Identity resources as separate from application desired state.
- Which fields are application-supplied versus platform-generated.

Update:

- [Application contract](../../../architecture/application-contract.md)
- [Application declaration reference](../../../developers/application-spec.md)
- [Security and authorization](../../../architecture/security-and-authorization.md)
- [Application lifecycle](../../../architecture/application-lifecycle.md)

The capability endpoint must advertise only implemented behavior. Planned
application identity must not appear there until PLAN-009 delivers it.

## 6. Add neutral contract fixtures

Add two neutral, digest-pinned `v1alpha2` declarations:

- A provider with public API, private worker, readiness, resources, and
  PostgreSQL.
- A consumer with public entry point, private worker, PostgreSQL, and provider
  DNS/443 egress.

These fixtures prove that:

- The existing schema accepts the intended generic topology.
- The generated provider hostname matches the egress declaration.
- Each project receives a separate database.
- Unsupported fields fail explicitly.
- No identity secret appears in desired state.
- No fixture or test references ODIP, VEF, datasets, or optimization.

They are generic examples or test fixtures, not deployable energy-system
profiles.

## 7. Add contract tests

Extend the specification tests to cover:

- Neutral provider and consumer declarations.
- Public-hostname derivation.
- Component-scoped egress generation.
- DNS address pinning and reapplication.
- Digest resolution.
- Separate database bindings.
- Resource and readiness validation.
- Secret redaction.
- Rejection of undeclared cross-project bindings.
- Rejection of unsupported identity fields until PLAN-009 exists.

No live cross-project authentication test belongs in PLAN-016 because the
identity capability does not exist yet.

## 8. Update the backlog with explicit outcomes

For each fit-gap item, record one of:

- Supported and verified.
- Accepted first-release limitation.
- Required implementation in PLAN-009.
- Required monitoring correction in PLAN-017.
- Blocker that must be implemented before PLAN-016 can close.

The accepted decisions remove the earlier PostgreSQL TLS, secret-scope, public
topology, retention, and classification ambiguity. The October 11, 2026 owner
confirmation also closes whether the applications fit current resource and
execution limits, require durable storage beyond PostgreSQL, or can supply the
classification and domain-retention records. The remaining work is
implementation, declaration validation, and acceptance evidence.

## Definition of done

PLAN-016 is complete when:

- The generic provider/consumer contract is accepted.
- The accepted topology, encryption, credential-scope, retention, and
  classification decisions remain recorded in ADR-020.
- Neutral `v1alpha2` fixtures validate successfully.
- Application repositories can supply their declarations without platform
  changes.
- No platform API, fixture, branch, default, or identity profile is
  application-specific.
- Every missing capability has an owner and subsequent task.
- Documentation and generated API contracts are consistent.
- Unit tests, OpenAPI freshness, documentation links, and `git diff --check`
  pass.

The following increment is PLAN-009: implement the generic human and machine
authentication and authorization flows specified in the
[energy-system use-case enablement plan](energy-system-integration.md#2-deliver-hosted-application-identity).
Start with the provider-neutral application-principal, application-group, and
access-policy contracts, then deliver explicit `browser-session` and
`bearer-token` route modes. The platform derives the browser callback/client and
machine audience/client, while applications declare only route/method rules,
modes, allowed application groups, and service-access targets. Implement browser
Authorization Code with PKCE through the reference authentication proxy,
confidential `client_credentials`, first-login human requests, pre-authorized
machine principals, the normalized principal/group context, and platform group
checks. Use an application-specific OAuth2 Proxy configuration plus the shared
replicated authorizer, Keycloak client roles mapped to scoped group claims,
PostgreSQL-authoritative durable reconciliation, and first-class access
resources. Apply the accepted five-minute token/snapshot/claim-refresh bound,
30-minute idle/eight-hour browser session, 24-hour maximum client-rotation
overlap, immutable policy revisions, and outward-only recovery reconciliation.
The increment is not complete until its tests cover browser redirect, cookie,
logout and CSRF behavior; deny pending, unapproved, wrong-group, anonymous, or
stale-policy requests; reject forged identity/group headers, direct-backend
bypass, wrong or expired bearer tokens, ambiguous paths and overlapping rules;
and verify request retention, attribute opt-in, rotation and recovery behavior.
