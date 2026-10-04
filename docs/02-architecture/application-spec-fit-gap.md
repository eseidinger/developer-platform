# ApplicationSpec fit-gap

Status: working analysis for PLAN-002 and DEV-001-T01, as of October 4, 2026. It compares the [v1alpha1 draft](application-spec.md) and planned Phase 2A successor with the implemented `PUT /projects/{name}` contract. Dispositions: **implemented**, **map** (exists internally, needs public form), **reject** (must fail validation until supported), **new** (work required).

## Fields

| Draft field | Current behaviour | Disposition | Decision / work |
|---|---|---|---|
| `apiVersion`, `kind` | Implemented: envelope accepted next to the flat body; OpenAPI committed at `docs/api/openapi.json` | implemented | Accept a versioned envelope alongside the flat body; flat body is treated as `v1alpha1` with a documented sunset. Publish an OpenAPI schema. |
| `metadata.name` | `name` path and body field, validated slug | map | Keep the slug; must equal the path parameter. |
| `metadata.project`, `metadata.environment` | One project per slug; one default environment, internal only | reject | Accept only `project == name` and `environment == default` until multi-environment work; reject other values. |
| `runtime.type` | Always a container | map | Accept only `container`. |
| `runtime.image` | `image`, validated and resolved to a digest at acceptance (`resolved_image`) | implemented | Digest is stored in the revision. Private registries remain unsupported. |
| `endpoints[].name/protocol/exposure` | One implicit public HTTP endpoint | reject | Accept exactly one `http` endpoint with `public` exposure; reject others. |
| `endpoints[].port` | `port`, 1024–65535, default 8080 | implemented | Map to the endpoint port. |
| `scaling` | Fixed single replica | reject | Accept `minInstances == maxInstances == 1`; reject autoscaling (see PLAN-004). |
| `resources.cpu/memory` | Fixed `100m/128Mi` requests and `500m/256Mi` limits for every workload | implemented (flat form) | Decided: explicit `requests`/`limits` with `requests <= limits`, defaults equal to the previous fixed values. Optional `resources` in the flat body is validated, canonicalized, stored in the revision and applied to the container; maxima keep two surge pods within the namespace quota. The enveloped `spec.application.resources` form follows with the envelope. |
| `health.readiness` | `probe_profile` (`status`, `hello-world`) with fixed paths | map | Public `path`/`port` replace the profile; keep `probe_profile` as a deprecated alias. Path validation required. |
| `spec.resources[type=postgres]` | A database is always provisioned | map | Make the single `postgres` resource explicit with profile `shared-dev` and `deletionPolicy: retain`; reject other types and profiles. |
| `configuration.values` | Not supported | reject | Reject until implemented; then non-secret strings with name collision checks. |
| `configuration.secrets` | Not supported | reject | Reject; needs a secret store (not in the current scope). |
| `bindings` | Fixed `PG*` variables | map | Accept only the default `PG` binding until configurable prefixes land; document the migration to `DB_*`. |
| `components[]` | One implicit long-running component | new | Add only in a successor schema. Migrate the singular application to one named `service`; preserve old revisions and rollback. |
| `components[].type` | No component type | new | Support `service` and `scheduled`; reject every other type before side effects. |
| `components[].ports` | One implicit public HTTP port | new | Give services named internal ports and stable discovery; scheduled components cannot expose ports publicly. |
| `components[].schedule` | No application scheduler | new | Accept a five-field cron expression, UTC, and `Forbid` concurrency for `scheduled` components only. Report run identity and outcome. |

## Cross-cutting items

| Item | State | Work |
|---|---|---|
| Unknown fields | Rejected (`extra="forbid"`) | Keep in the envelope. |
| Public `namespace` in responses | Not in `/projects` or operation output; only the platform-admin security-configuration inspection returns the Namespace manifest | Done; no public change needed. |
| Capability profiles | `GET /v1/capabilities` publishes the `default` environment profile; PUT rejections return `code` `unsupported_capability` or `invalid_spec` | Implemented; the profile is static code, not yet per-environment configuration. |
| Revision identity | Spec equality with the resolved digest | Keep; extend the equality to resource fields. |
| Idempotency and conflicts | Same-revision reuse only | PLAN-003 (expected revision, idempotency keys). |
| Component capability profile | Not published | DEV-001-T01: advertise long-running components, internal discovery, and scheduled components independently; reject unsupported requests before side effects. |

## Open decisions

1. ~~CPU and memory semantics.~~ Decided on explicit `requests` and `limits` with defaults equal to the earlier fixed values, so existing projects do not change.
2. **Flat body sunset.** (Both forms are accepted today.) How long the flat body is accepted next to the envelope.
3. ~~Health in the first envelope.~~ Interim `health.readiness.profile` (same values as `probe_profile`); `path`/`port` are rejected until supported.

## Proposed order

1. Retain the completed `v1alpha1` resource semantics, envelope/OpenAPI, and capability/error work as the migration baseline.
2. Define the successor `components` schema and single-service compatibility mapping.
3. Add service discovery and independently reconciled long-running component status.
4. Add scheduled-component validation, execution, run status, and capability rejection.
5. Prove migration/rollback before making the successor schema the preferred form.
