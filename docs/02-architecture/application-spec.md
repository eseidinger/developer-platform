# ApplicationSpec

Status: **v1alpha1 contract draft**, including environment, health, deletion protection, and validation rules. This is neither an implemented schema nor a ready-to-deploy manifest.

## Difference from the current API

The implemented [project contract](../../platform/README.md#project-specification) is JSON with `name`, `image`, optional `port` and `probe_profile`, submitted to `PUT /projects/{name}`. It has no public schema version, optional resource selection, or configurable bindings. PostgreSQL is always provisioned; bindings use `PG*` variables. The persistence layer now assigns a stable internal project ID while retaining `name` as the public slug and existing authorization scope. Each project has a default environment and one application with stable IDs; desired specs are retained as immutable, numbered revisions, with identical specs reusing the current revision. These catalog IDs and revisions are not yet part of the public API.

The database defines a versioned application-operation envelope/result table. PUT stores the desired revision and queued operation atomically, returning `202 Accepted` with an operation ID and `GET /v1/operations/{id}` status reference. Operation reads check the caller's current project-view grant, audit access, and redact results. The in-process Python worker executes idempotent provider steps and reclaims interrupted `running` operations after restart. `POST /projects/{name}/restart` queues a `restart` operation on the current revision; the worker re-applies only the Deployment with a pod-template annotation set to the operation ID, so retries cannot restart twice. On acceptance, PUT resolves the image tag to an immutable digest with anonymous registry access only (HEAD manifest request over HTTPS, no redirects, token realm limited to the registry or its Docker Hub token host) and stores `resolved_image` (`<repository>@sha256:…`) in the revision, so the deployed image, the revision and the readiness comparison use the digest. Only registries in `IMAGE_REGISTRIES` (default `docker.io,ghcr.io,quay.io`) are contacted; others are rejected with 422, a missing tag with 422 and a registry outage with 503, all before any catalog or provider side effect. An unchanged tag/digest reuses the revision; a moved tag creates a new revision. Legacy revisions without `resolved_image` deploy their tag. Private registries and credentials are not supported. Operation state reports resource application; a separate live readiness snapshot reports desired/ready replicas, applied and active images, and rollout diagnostics without changing the operation state.

Unknown project request fields are rejected by the current endpoint before catalog or provider side effects. Capability rejection and secret references below remain target requirements; sending this YAML or adding its fields to a current project request does not implement them. The internal catalog migration does not version or replace the public API contract; the field-level fit-gap is in [application-spec-fit-gap.md](application-spec-fit-gap.md) and the migration remains PLAN-002 work. See [ADR-012](../03-decisions/ADR-012-admin-provisioning-baseline.md).

## Purpose and scope

A spec describes the desired runtime state of a catalog application in a catalog project/environment: workload, required resources, bindings, and configuration. The control plane produces observed status separately. Application ownership, membership, and grants are catalog operations, not fields that a deployment spec can mutate. Docker networks, Kubernetes namespaces, and PostgreSQL server addresses are outside this contract.

The first profile supports one OCI image, one HTTP endpoint, and optional PostgreSQL. Object storage, messaging, cache, autoscaling, and multiple components are later capabilities. Unknown fields and unsupported capabilities must not be silently ignored.

## Example

The domain and image are fictitious. On acceptance, the tag is resolved to an immutable digest and recorded in the deployment. The server profile selects a supported PostgreSQL version; individual databases on a shared server cannot independently choose an engine version.

```yaml
apiVersion: platform.example/v1alpha1
kind: Application
metadata:
  name: price-service
  project: procurement
  environment: dev
spec:
  application:
    runtime:
      type: container
      image: registry.example.com/price-service:1.4.2
    endpoints:
      - name: api
        protocol: http
        port: 8080
        exposure: public
    scaling:
      minInstances: 1
      maxInstances: 1
    resources:
      cpu: "0.5"
      memory: 512Mi
    health:
      readiness:
        path: /health/ready
        port: 8080
  resources:
    - name: database
      type: postgres
      profile: shared-dev
      deletionPolicy: retain
  configuration:
    values:
      LOG_LEVEL: INFO
    secrets:
      - name: external-api-key
        target: EXTERNAL_API_KEY
        source:
          type: platform-secret
          key: pricing-api
    bindings:
      - resource: database
        as: DB
```

Before accepting the spec, the control plane resolves the project, environment, and application to stable catalog IDs and verifies the caller's current deployment grant. A dependency or machine-to-resource grant, such as allowing `reporting-service` to read the database, is created through the catalog contract and enforced by the control-plane/provider path; it is not smuggled into a deployment update.

Catalog relationships are descriptive and do not provision anything by themselves. The `resources` and `bindings` sections request their environment-specific runtime realization; the control plane rejects a request that conflicts with catalog relationships, authorization, or platform policy.

## Fields and semantics

| Field | Meaning |
|---|---|
| `apiVersion`, `kind` | Explicit schema family and version |
| `metadata.name/project/environment` | Human-readable catalog references resolved to stable IDs; a deployment cannot create, rename, or move those catalog records |
| `application.runtime` | Portable executable artifact |
| `endpoints` | Named HTTP targets; `internal` describes network exposure, not authentication |
| `scaling` | Equal limits specify a fixed instance count; different limits require autoscaling capability |
| `resources.cpu/memory` | Requested CPU/memory budget; the provider must enforce the promised semantics |
| `spec.resources` | Logical external resources, separate from workload compute |
| `profile` | Platform-managed service profile with explicit capabilities and limitations |
| `deletionPolicy` | Initially `retain` for PostgreSQL; no data deletion as a side effect of application deletion |
| `configuration.values` | Non-secret string values |
| `configuration.secrets` | References to authorized secret objects, never plaintext values |
| `bindings` | Inject a resource into the runtime under a defined prefix |

The example produces `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, and `DB_PASSWORD`. Binding names are stable; values can change during rotation or migration. Credentials are delivered only to the authorized workload, never returned in status.

## Validation and authorization

1. Check schema version, required fields, unique names, positive resource values, and valid ports.
2. Resolve application/project/environment through the catalog and check its versioned permission facts. The spec is not an identity or authority source.
3. Resolve secret and resource references; disallow implicit cross-project bindings.
4. A `developer` can change deployments but cannot grant additional access. Ownership, membership, dependency, and grant changes use separate authorized catalog operations.
5. Check capabilities, quotas, service profiles, and resource limits. A shared-database profile does not promise a hard storage quota per database.
6. Check binding prefixes and configuration/secret target names for collisions.
7. Generate a plan and new revision; identical specs are semantically idempotent.

## Contract work required for Phase 2

The draft currently exposes one CPU/memory budget. It does not yet define separate requests and limits required by DEV-008 and OPS-005. Resolve those portable semantics, their validation, and the schema migration in PLAN-002 before accepting scaling/policy tasks; do not silently interpret one budget as two independently configurable values. The first profile remains one image and one HTTP endpoint, with a fixed replica count; multiple replicas do not imply multiple components.

## Status and evolution

Status includes at least `desiredRevision`, `observedRevision`, `phase`, `conditions`, `operationId`, and authorized endpoint information. Conditions carry timestamps, reasons, and redacted messages. Secret values and administrative provider credentials are excluded.

Breaking changes require a new schema version and migration path. Multi-component support needs a separate contract design; the existing `application` object must not silently become a list. The catalog's principals/grants model is a separate versioned contract, not a second syntax inside ApplicationSpec.

Core decision: [ADR-001](../03-decisions/ADR-001-platform-api-abstraction.md). Permissions: [Security](security.md). UI/API options: [ADR-007](../03-decisions/ADR-007-ui-api-deployment.md).
