# ApplicationSpec

Status: **v1alpha1 contract draft**, including environment, health, deletion protection, and validation rules. This is neither an implemented schema nor a ready-to-deploy manifest.

## Purpose and scope

A spec describes the desired state of an application in a project/environment: workload, required resources, configuration, and access. The server produces observed status separately. Docker networks, Kubernetes namespaces, and PostgreSQL server addresses are outside this contract.

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
  owner: team-a
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
  access:
    humans:
      - subject:
          type: group
          name: developers
        role: developer
    machines:
      - subject:
          type: application
          name: reporting-service
        permissions:
          - resource: database
            actions: [read]
```

The final grant requires an existing application identity in the same project/environment. It is allowed only if the submitter can manage access and the provider can correctly enforce database read permissions, including future objects. Otherwise, the spec is rejected.

## Fields and semantics

| Field | Meaning |
|---|---|
| `apiVersion`, `kind` | Explicit schema family and version |
| `metadata.name/project/environment` | Stable resource identity; cannot move scopes through a rename after creation |
| `metadata.owner` | Ownership metadata, not an automatic permission grant |
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
| `access.humans/machines` | Permission assignments; internally normalizable to Principal–Resource–Action |

The example produces `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, and `DB_PASSWORD`. Binding names are stable; values can change during rotation or migration. Credentials are delivered only to the authorized workload, never returned in status.

## Validation and authorization

1. Check schema version, required fields, unique names, positive resource values, and valid ports.
2. Check project/environment against request scope and permissions. The spec is not an authority source.
3. Resolve secret, resource, and principal references; disallow implicit cross-project bindings.
4. A `developer` can change deployments but cannot grant additional access. Changes to `access` require separate administrative permissions.
5. Check capabilities, quotas, service profiles, and resource limits. A shared-database profile does not promise a hard storage quota per database.
6. Check binding prefixes and configuration/secret target names for collisions.
7. Generate a plan and new revision; identical specs are semantically idempotent.

## Status and evolution

Status includes at least `desiredRevision`, `observedRevision`, `phase`, `conditions`, `operationId`, and authorized endpoint information. Conditions carry timestamps, reasons, and redacted messages. Secret values and administrative provider credentials are excluded.

Breaking changes require a new schema version and migration path. Multi-component support needs a separate contract design; the existing `application` object must not silently become a list. The future `principals/grants` model is a possible next version, not a second simultaneously valid syntax.

Core decision: [ADR-001](../03-decisions/ADR-001-platform-api-abstraction.md). Permissions: [Security](security.md). UI/API options: [ADR-007](../03-decisions/ADR-007-ui-api-deployment.md).
