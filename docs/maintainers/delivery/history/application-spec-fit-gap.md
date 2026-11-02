# ApplicationSpec fit-gap (historical)

Status: working analysis for PLAN-002 and DEV-001-T01, as of October 4, 2026. It
compares the [v1alpha1 draft](../../../architecture/application-contract.md) and
planned Phase 2A successor with the implemented `PUT /projects/{name}` contract.
Dispositions: **implemented**, **map** (exists internally, needs public form),
**reject** (must fail validation until supported), **new** (work required).

## Fields

- **Draft field:** `apiVersion`, `kind`
  - **Current behaviour:** Implemented: envelope accepted next to the flat body;
    OpenAPI committed at `docs/api/openapi.json`
  - **Disposition:** implemented
  - **Decision / work:** Accept a versioned envelope alongside the flat body;
    flat body is treated as `v1alpha1` with a documented sunset. Publish an
    OpenAPI schema.
- **Draft field:** `metadata.name`
  - **Current behaviour:** `name` path and body field, validated slug
  - **Disposition:** map
  - **Decision / work:** Keep the slug; must equal the path parameter.
- **Draft field:** `metadata.project`, `metadata.environment`
  - **Current behaviour:** One project per slug; one default environment,
    internal only
  - **Disposition:** reject
  - **Decision / work:** Accept only `project == name` and
    `environment == default` until multi-environment work; reject other values.
- **Draft field:** `runtime.type`
  - **Current behaviour:** Always a container
  - **Disposition:** map
  - **Decision / work:** Accept only `container`.
- **Draft field:** `runtime.image`
  - **Current behaviour:** `image`, validated and resolved to a digest at
    acceptance (`resolved_image`)
  - **Disposition:** implemented
  - **Decision / work:** Digest is stored in the revision. Private registries
    remain unsupported.
- **Draft field:** `endpoints[].name/protocol/exposure`
  - **Current behaviour:** One implicit public HTTP endpoint
  - **Disposition:** reject
  - **Decision / work:** Accept exactly one `http` endpoint with `public`
    exposure; reject others.
- **Draft field:** `endpoints[].port`
  - **Current behaviour:** `port`, 1024–65535, default 8080
  - **Disposition:** implemented
  - **Decision / work:** Map to the endpoint port.
- **Draft field:** `scaling`
  - **Current behaviour:** Fixed single replica
  - **Disposition:** reject
  - **Decision / work:** Accept `minInstances == maxInstances == 1`; reject
    autoscaling until the Phase 2C scaling and policy package supports it.
- **Draft field:** `resources.cpu/memory`
  - **Current behaviour:** Fixed `100m/128Mi` requests and `500m/256Mi` limits
    for every workload
  - **Disposition:** implemented (flat form)
  - **Decision / work:** Decided: explicit `requests`/`limits` with
    `requests <= limits`, defaults equal to the previous fixed values. Optional
    `resources` in the flat body is validated, canonicalized, stored in the
    revision and applied to the container; maxima keep two surge pods within the
    namespace quota. The enveloped `spec.application.resources` form follows
    with the envelope.
- **Draft field:** `health.readiness`
  - **Current behaviour:** `probe_profile` (`status`, `hello-world`) with fixed
    paths
  - **Disposition:** map
  - **Decision / work:** Public `path`/`port` replace the profile; keep
    `probe_profile` as a deprecated alias. Path validation required.
- **Draft field:** `spec.resources[type=postgres]`
  - **Current behaviour:** A database is always provisioned
  - **Disposition:** map
  - **Decision / work:** Make the single `postgres` resource explicit with
    profile `shared-dev` and `deletionPolicy: retain`; reject other types and
    profiles.
- **Draft field:** `configuration.values`
  - **Current behaviour:** Not supported
  - **Disposition:** reject
  - **Decision / work:** Reject until implemented; then non-secret strings with
    name collision checks.
- **Draft field:** `configuration.secrets`
  - **Current behaviour:** Not supported
  - **Disposition:** reject
  - **Decision / work:** Reject; needs a secret store (not in the current
    scope).
- **Draft field:** `bindings`
  - **Current behaviour:** Fixed `PG*` variables
  - **Disposition:** map
  - **Decision / work:** Accept only the default `PG` binding until configurable
    prefixes land; document the migration to `DB_*`.
- **Draft field:** `components[]`
  - **Current behaviour:** One implicit long-running component
  - **Disposition:** new
  - **Decision / work:** Add only in a successor schema. Migrate the singular
    application to one named `service`; preserve old revisions and rollback.
- **Draft field:** `components[].type`
  - **Current behaviour:** No component type
  - **Disposition:** new
  - **Decision / work:** Support `service` and `scheduled`; reject every other
    type before side effects.
- **Draft field:** `components[].ports`
  - **Current behaviour:** One implicit public HTTP port
  - **Disposition:** new
  - **Decision / work:** Give services named internal ports and stable
    discovery; scheduled components cannot expose ports publicly.
- **Draft field:** `components[].schedule`
  - **Current behaviour:** No application scheduler
  - **Disposition:** new
  - **Decision / work:** Accept a five-field cron expression, UTC, and `Forbid`
    concurrency for `scheduled` components only. Report run identity and
    outcome.

## Cross-cutting items

- **Item:** Unknown fields
  - **State:** Rejected (`extra="forbid"`)
  - **Work:** Keep in the envelope.
- **Item:** Public `namespace` in responses
  - **State:** Not in `/projects` or operation output; only the platform-admin
    security-configuration inspection returns the Namespace manifest
  - **Work:** Done; no public change needed.
- **Item:** Capability profiles
  - **State:** `GET /v1/capabilities` publishes the `default` environment
    profile; PUT rejections return `code` `unsupported_capability` or
    `invalid_spec`
  - **Work:** Implemented; the profile is static code, not yet per-environment
    configuration.
- **Item:** Revision identity
  - **State:** Spec equality with the resolved digest
  - **Work:** Keep; extend the equality to resource fields.
- **Item:** Idempotency and conflicts
  - **State:** Same-revision reuse only
  - **Work:** PLAN-003 (expected revision, idempotency keys).
- **Item:** Component capability profile
  - **State:** Not published
  - **Work:** DEV-001-T01: advertise long-running components, internal
    discovery, and scheduled components independently; reject unsupported
    requests before side effects.

## Open decisions

1. ~~CPU and memory semantics.~~ Decided on explicit `requests` and `limits`
   with defaults equal to the earlier fixed values, so existing projects do not
   change.
1. **Flat body sunset.** (Both forms are accepted today.) How long the flat body
   is accepted next to the envelope.
1. ~~Health in the first envelope.~~ Interim `health.readiness.profile` (same
   values as `probe_profile`); `path`/`port` are rejected until supported.

## Proposed order

1. Retain the completed `v1alpha1` resource semantics, envelope/OpenAPI, and
   capability/error work as the migration baseline.
1. Define the successor `components` schema and single-service compatibility
   mapping.
1. Add service discovery and independently reconciled long-running component
   status.
1. Add scheduled-component validation, execution, run status, and capability
   rejection.
1. Prove migration/rollback before making the successor schema the preferred
   form.
