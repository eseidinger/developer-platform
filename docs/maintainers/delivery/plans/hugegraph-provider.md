# HugeGraph Provider — Next Data Store Increment

Status: selected on November 3, 2026; planning only, no source implementation
or fixture evidence yet. This plan refines
[Phase 8 package 8.4](phase-8-deferred-data-stores.md#84-graph-stores) and
[PLAN-038](../backlog.md#data-store-expansion-tasks). It complements
[package 7.4](phase-7-planned-data-stores.md#74-graph-data) (AGE/Neo4j); it does
not replace or re-open that package. Phase 7's unfinished acceptance and the
other Phase 8 packages remain independent. The existing
[store policies](data-store-expansion.md) apply, including the
[store selection decision](data-store-expansion.md#store-selection-decision):
no benchmark, domain-need or comparative-success requirement gates this
selection.

## Scope and decisions

- Add Apache HugeGraph (Apache top-level project, Apache License 2.0) as an
  optional, shared Docker Compose service with the embedded RocksDB backend.
  Each named platform resource maps to a separate HugeGraph graph space;
  application deployment never creates one implicitly. Unlike the
  [Neo4j Community dedicated-instance exception](data-store-expansion.md#neo4j-community-dedicated-instance-decision),
  HugeGraph supports multiple graph spaces per server and per-graph role
  permissions, so the default
  [shared-service model](data-store-expansion.md#shared-service-placement-decision)
  applies; no dedicated-instance exception is requested. PostgreSQL remains
  the platform's own catalog and the reference for later comparisons.
- Use the official `hugegraph/hugegraph` distribution under Apache License
  2.0. Record the exact image digest, bundled component notices and supported
  client versions before installation. Pin upgrades under the shared-store
  maintenance policy.
- Keep project data authoritative unless an application explicitly identifies a
  recoverable source. The supported backup/restore tooling of the pinned
  distribution over the RocksDB backend must be verified; it is not a
  substitute for a protected, point-in-time encrypted off-host backup.
- Reuse project ownership, cross-project approval, explicit component
  bindings, human lease durations, application credential rotation and separate
  confirmed purge. Do not expose the server administrator, user/role
  management, Gremlin-Server administration or server configuration to
  project clients.
- Query surfaces are the REST API and Gremlin (plus HugeGraph-PQL where
  supported by the pinned release). Application bindings inject the private
  REST/Gremlin endpoints, graph name and scoped credentials (for example
  `HUGEGRAPH_REST_URI`, `HUGEGRAPH_GREMLIN_URI`, `HUGEGRAPH_GRAPH`,
  `HUGEGRAPH_USERNAME`, `HUGEGRAPH_PASSWORD`); the exact binding key set is
  fixed during the platform-contract step below.

## Access boundary to resolve before enabling the provider

HugeGraph's built-in auth manages users and roles with per-graph permissions;
a native read-only role exists per graph space, so the common
read-only/read-write distinction applies (unlike Neo4j Community). Verify the
pinned release's actual role/permission semantics before relying on them; see
the [HugeGraph security guide](https://hugegraph.apache.org/docs/guides/security/)
and [auth API](https://hugegraph.apache.org/docs/clients/restful-api/auth/).

1. Give each resource private access to only its graph space, with separate
   platform-managed human and application identities. Route every client
   request through the access gateway; only the operator API and trusted relay
   may reach HugeGraph directly. Verify that a credential cannot enumerate or
   access another graph, another project's data, or server-level APIs.
   Graph names alone provide no isolation.
1. Map read-only grants to the verified native per-graph read role. Prove
   enforcement for writes across all exposed surfaces (REST write APIs,
   Gremlin mutations, PQL), including encoded paths, batch APIs and
   administrative endpoints; reject by route and operation, not merely by
   HTTP method or protocol. A read-only grant must never become a full-access
   credential with an unrestricted network path.
1. Fence both new and established access at lease expiry, revocation, rotation
   and retirement, including HTTP keep-alive, Gremlin sessions and browser
   sessions. Keep service administrator credentials separate from resource
   bindings and redact them from API responses, logs and backups exposed to
   projects.
1. Let authorized resource writers manage their graph's schema (property keys,
   vertex/edge labels, indexes) within that graph only. User/role management,
   server configuration and cross-graph administration remain operator-only.
   Validate allowed operations and audit changes; reject unsupported
   administrative operations explicitly instead of silently upgrading
   permissions.
1. Provide private REST/Gremlin client access first. Add HugeGraph-Hubble (or
   a platform browser console) only after proving the same scoped, revocable
   behavior through the lease relay; otherwise advertise browser access as
   unsupported.

## Ordered implementation work

1. **Compatibility and capacity:** Validate the pinned HugeGraph release and
   official image in a disposable local fixture. Check license and bundled
   notices, per-graph role/permission semantics, credential/session
   invalidation, published security advisories, the distribution's supported
   backup/restore method over RocksDB, health and metrics endpoints, and
   CPU/memory/disk headroom with all selected stores running. Record the
   implementation owner and resource budget in PLAN-038.
1. **Service foundation:** Add an opt-in Compose/Ansible service (`hugegraph`
   profile) with persistent RocksDB storage, private networking, bounded
   resources, health checks, pinned image, administrator secret management and
   an operator runbook. No public HugeGraph REST/Gremlin port or Docker socket
   reaches applications or the Platform API.
1. **Platform contract:** Add `hugegraph` to the provider catalog, API schema,
   generated UI types, CLI and portal. Implement named graph-space
   create/inspect, reconciliation, explicit component bindings, credential
   issue/revoke/rotate, retirement and confirmed purge. Set per-graph security
   at creation before granting client access; fail closed if setup is
   incomplete.
1. **Data and security tests:** Verify vertex/edge create/update/delete,
   Gremlin and PQL queries, schema and index management with representative
   fixtures. Exercise same-project and cross-project grants, reader/writer
   separation, system API denial, session fencing, service restart and
   partial provisioning retries. Test browser access if implemented.
1. **Operations:** Integrate service and per-resource health, bounded metrics,
   alerts, capacity admission and quota reporting. Record any monitoring-only
   quota limit explicitly; never call it a hard per-graph quota. Capture
   consistent encrypted off-host backups on the selected 12-hour schedule,
   including graph data, auth configuration and credential reconciliation
   inputs. Preserve the existing purge backup gate and test backup capture
   before Phase 8 acceptance.
1. **Acceptance and handoff:** Run offline checks, focused component tests and
   bounded deployed tests for the activated provider. Record revision, image
   digest, environment, evidence and limitations in PLAN-038. The off-host
   restore, fresh credential issuance and application reconnection drill
   remains
   [Phase 10 package 10.13](phase-10-anytime-leftovers.md#1013-verify-deployed-data-store-recovery-plan-027plan-033-follow-up).
   Compare HugeGraph with Neo4j Community and Apache AGE in
   [Phase 9 package 9.3](phase-9-store-measurement-and-comparison.md#93-graph)
   and as an activated deferred store in
   [package 9.5](phase-9-store-measurement-and-comparison.md#95-deferred-store-comparisons);
   those comparisons do not gate provider selection or the Phase 8 exit.

## Phase 8 exit for HugeGraph

Provisioning, isolation, read-only and read-write access, active revocation,
bindings, retained-data lifecycle, monitoring, bounded capacity, backup capture
and safe purge pass with recorded evidence. Any unsupported capability is
rejected and documented. No deployed restore or performance result is claimed
by this exit; those checks retain their Phase 10 and Phase 9 owners.
