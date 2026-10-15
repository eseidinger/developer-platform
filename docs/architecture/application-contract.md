# Application contract

Status: current contract principles. Field-level syntax is documented in the
[application declaration reference](../developers/application-spec.md), and the
generated [OpenAPI document](../api/openapi.json) is machine-readable.

## Purpose

An application declaration describes desired platform state: components,
container images, endpoints, schedules, resources, health checks, PostgreSQL,
configuration, and permitted connectivity. It does not expose Kubernetes kinds,
Docker networks, namespaces, provider credentials, or database server addresses.

The platform resolves human-readable project and component names to stable
platform identities. Ownership, grants, and machine credentials are separate
resources; a deployment declaration cannot mutate authority.

## Current schema family

`platform.example/v1alpha2` is the preferred multi-component schema. It supports
long-running services, scheduled components, stable internal discovery, one
public service, component resources and readiness, and the current shared
PostgreSQL profile. The API also accepts the earlier `v1alpha1` envelope and flat
legacy form for compatibility.

Compatibility forms map into the same canonical desired state, revisions, and
operations. They are not separate provider implementations. A breaking semantic
change requires a new schema version and an explicit migration path; an existing
field must not silently acquire a different meaning.

## Contract principles

1. A deployment is a complete desired-state `PUT`, not a patch.
2. Unknown fields and unsupported capabilities fail before provider side effects.
3. The environment capability endpoint advertises supported features; clients do
   not infer support from Kubernetes details.
4. Image tags are resolved to immutable digests before a revision is accepted.
5. Semantically identical desired state reuses the current revision.
6. `If-Match` protects updates from stale writers.
7. Accepted intent, provider application, and live readiness are distinct states.
8. Secret values and provider credentials never appear in ordinary status,
   diagnostics, audit records, or generated plans.
9. PostgreSQL data is retained independently of workload lifecycle.
10. Provider portability is a contract constraint, not a requirement to operate a
    second provider.

## Planned application metrics capability (Phase 4)

A service component may opt in to platform collection of Prometheus-format
application metrics by declaring a bounded metrics path and one of its declared
HTTP ports. The exact versioned field shape remains to be designed and is not
accepted by the current `v1alpha2` API. The capability must be advertised by the
environment before a declaration can use it. Unknown or unsupported metrics
fields fail before provider side effects; existing declarations remain valid.

The platform derives scrape targets from the accepted project/component identity
and reaches them on a private, platform-controlled path. Metrics collection must
not add a public route, bypass application access policy, or accept arbitrary
URLs, scrape credentials, or caller-supplied project labels. Bound sample count,
series cardinality, response size, scrape rate and retention to the lab budget.
Allow only Public or Internal metric names and label values; reject or drop
secrets, personal data, raw paths with identifiers and unbounded labels.
Operators may use the shared Prometheus/Grafana backends; project readers receive
only fixed project-scoped views through the Platform API. Missing or failed
scrapes are explicit, not healthy zeros. See [Phase 4](../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md#43-collect-hosted-application-metrics-plan-023).

## Planned application tracing capability (Phase 4)

Service and scheduled components may opt in to a private OpenTelemetry trace
export path. The exact versioned declaration is not accepted by the current
`v1alpha2` API; the environment must advertise support before it can be used.
The platform supplies a private OTLP endpoint and verified project/application/
component identity. A workload cannot choose its own project identity through
span attributes, and a declaration cannot configure an arbitrary exporter URL
or bypass the authenticated application access boundary.

Safe W3C trace context may cross the platform boundary and permitted internal
calls, but it conveys no authority. Incoming external baggage and trace metadata
are untrusted. Raw traces remain operator-only; any project-facing read is a
fixed, bounded, server-scoped Platform API view. Span export excludes secrets,
personal data, bodies, SQL text and raw identifier-bearing URLs, with explicit
sampling and storage limits. See [Phase 4](../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md#44-let-hosted-applications-participate-in-tracing-plan-024).

## Generic cross-project integration profile

The initial hosted-application integration profile permits one public component
per project. Cross-project calls use public HTTPS and caller-declared DNS/443
egress; DNS addresses are fixed when the deployment is applied and require an
explicit reapply when they change. Browser and confidential service identities
are separate resources and cannot be created or authorized by an application
declaration. A separate `ApplicationAccessPolicy` selects `browser-session` or
`bearer-token`, allowed project-scoped application groups, and explicit
non-overlapping route/method matches on the public component. The platform
derives the standard browser callback, OIDC client, machine audience, session
behavior, group-claim mapping, and credential lifecycle. Applications do not
submit redirect URIs, audiences, OAuth scopes, identity-provider group paths, or
proxy configuration in the initial profile.

The reference profile uses one identity realm per platform environment, with
separate application clients and audiences rather than application-specific
realms. Humans use first-login enrollment: authentication creates a pending
access request with no authority, and a provider project administrator assigns
application groups before access succeeds. Machine principals are
pre-authorized: the provider approves a service-access request and its groups
before the consumer credential becomes usable. Platform and project roles do
not imply application-group membership.

The Keycloak reference adapter maps each stable application-group ID to an
application-client role and emits relevant roles in a client-scoped `groups`
claim. One platform-managed OAuth2 Proxy configuration per public application
handles browser OIDC; a shared replicated authorizer handles route policy,
machine tokens, first-login recording, revocation overrides, and normalized
headers. These are provider details rather than application inputs.

The initial policy language allows only non-empty `anyOfGroups` on exact or
segment-aware prefix matches with explicit methods. Overlaps and ambiguous paths
are rejected, unmatched routes are denied, and every public application route
requires `browser-session` or `bearer-token`; anonymous routes are unsupported.
Policies use immutable atomically activated revisions. Authorization snapshots,
machine tokens, and browser claim refresh are bounded to five minutes and fail
closed after expiry. [ADR-020](decisions/ADR-020-generic-hosted-application-integration.md)
defines request retention, session lifetime, credential rotation, and recovery
reconciliation.

On each admitted request, the platform boundary supplies the normalized caller
and stable group IDs through reserved `X-Platform-Principal-*` headers.
Application middleware reads that context; it does not parse platform sessions
or bearer tokens. The platform has already performed coarse route
authorization. Applications own only finer object-, row-, or domain-level
decisions that cannot be represented by the route policy. Display name is
released only by explicit policy opt-in; email additionally requires classified
personal-data handling. Neither is an authorization key.

PostgreSQL remains a per-project retained resource, but its traffic is outside
the initial encrypted-channel requirement and is not TLS-protected. Application
secrets are project-scoped and may be visible to every component in the project.
These are explicit first-release limits, not application-specific behavior.

Applications own domain data, fine-grained domain authorization, and row-level
retention. The platform owns application-group lifecycle, coarse route
authorization, infrastructure retention, and handling boundaries. Projects
declare classification as governance metadata separate from desired deployment
state. [ADR-020](decisions/ADR-020-generic-hosted-application-integration.md)
defines the accepted authentication, authorization, retention, and Public,
Internal, Confidential, and Restricted handling rules.

## Validation and authorization

The API validates schema, names, images, ports, resources, schedules, probes,
capabilities, quotas, connectivity policy, and project consistency before
persisting a new revision. It authenticates the issuer/subject pair and evaluates
the current platform grant for the requested project and action.

A durable operation rechecks authorization and revision freshness before making
infrastructure changes. Backend errors are translated into stable platform error
categories and redacted results. Cross-project bindings are never implicit.

## Evolution

New capabilities first require a bounded contract, capability advertisement,
rejection behavior on unsupported environments, migration/rollback rules, and
acceptance evidence. Optional provider or service extraction must preserve the
public concepts and identifiers described here. See
[Architecture evolution](evolution.md) and
[ADR-001](decisions/ADR-001-platform-api-abstraction.md).
