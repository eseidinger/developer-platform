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
