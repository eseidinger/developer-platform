# HugeGraph Provider — Next Data Store Increment

Status: selected on November 3, 2026; source provider, private REST relay,
Compose service, API/CLI/UI contract, monitoring and backup/restore volume
mapping implemented. The disposable pinned 1.7.0 fixture passes graph
provisioning, schema, vertex and edge operations, reader write denial, relay path
isolation, restart, container recreation, revocation and purge. Focused gateway
tests cover the platform browser console. Deployed
acceptance remains open; off-host backup capture verification belongs to Phase
10.13. This plan refines
[Phase 8 package 8.4](phase-8-deferred-data-stores.md#84-graph-stores) and
[PLAN-038](../backlog.md#data-store-expansion-tasks). It complements
[package 7.4](phase-7-planned-data-stores.md#74-graph-data) (AGE/Neo4j); it does
not replace or re-open that package. Phase 7's unfinished acceptance and the
other Phase 8 packages remain independent. The existing
[store policies](data-store-expansion.md) apply, including the
[store selection decision](data-store-expansion.md#store-selection-decision):
no benchmark, domain-need or comparative-success requirement gates this
selection.

On November 10, the Ansible deployment of revision
`66a056d90b5be038e21c86b5a00aac267c8689a7+dirty` passed. The read-only
Phase 8 host smoke verified HugeGraph container health, CPU/memory limits,
private ports, its three named persistent volumes and a native-up Prometheus
metric of 1. The image also declares an anonymous volume at
`/hugegraph-server`. Inspection found initialized configuration, the startup
marker and audit logs there; backup and restore source now include this parent
volume. The updated backup runner was installed on November 10 and the deployed
smoke confirmed the anonymous mount. A deployed off-host capture remains to be
verified in Phase 10.13. See
[EV-73 and EV-75](../backlog.md#verification-register).
Scoped deployed lifecycle remains open. On November 10, the owner reported
successful deployed browser checks with separate reader and writer identities,
reader write denial and access denial after grant revocation; see
[EV-74](../backlog.md#verification-register).

The fixture found that a native graph-scoped reader can still list graphs and
read another graph directly. The relay therefore rejects graph enumeration and
all paths outside the named graph for every client. Gremlin, Cypher, PQL and
upstream Hubble access remain unsupported; bounded REST graph/schema routes and
the lease-scoped platform browser console are exposed. See
the PLAN-039 pre-removal Git commit `632b921` for the reproducible fixture and
`hugegraph_access.py` path boundary. The image digest is
`sha256:077b89e1f2d5e228d99598bdb537161fb2e8a7b5abedf4724d97cf4de11529ba`.

## Scope and decisions

- Add Apache HugeGraph (Apache top-level project, Apache License 2.0) as an
  optional, shared Docker Compose service with the embedded RocksDB backend.
  Each named platform resource maps to a separate graph in the `DEFAULT`
  graph space, with a distinct RocksDB store and data/WAL paths;
  application deployment never creates one implicitly. Unlike the
  [Neo4j Community dedicated-instance exception](data-store-expansion.md#neo4j-community-dedicated-instance-decision),
  HugeGraph supports multiple graphs per server and graph-scoped authorization
  targets, so the default
  [shared-service model](data-store-expansion.md#shared-service-placement-decision)
  is the proposed model, subject to isolation tests. Graph spaces other than
  `DEFAULT` require HStore/PD and are outside this RocksDB plan. The
  [1.7 graph API](https://hugegraph.apache.org/versions/1.7/docs/clients/restful-api/graphs/)
  documents creating RocksDB graphs with distinct paths. PostgreSQL remains
  the platform's own catalog and the reference for later comparisons.
- Use a pinned `hugegraph/hugegraph` container image and verify its provenance,
  license and bundled notices against the signed Apache release. HugeGraph's
  Docker images are convenient project images, not official ASF release
  artifacts, as the
  [server quick start](https://hugegraph.apache.org/versions/1.7/docs/quickstart/hugegraph/hugegraph-server/)
  notes. The pinned image has no top-level `LICENSE` or `NOTICE` file in the
  inspected server tree. Compare its bundled components and notices with the
  signed Apache release before selecting it for deployment; that review is
  open. Record the exact image digest and supported client versions before
  installation. Pin upgrades under the shared-store maintenance policy.
- Keep project data authoritative unless an application explicitly identifies a
  recoverable source. The supported backup/restore tooling of the pinned
  distribution over the RocksDB backend must be verified; it is not a
  substitute for a protected, point-in-time encrypted off-host backup.
- Reuse project ownership, cross-project approval, explicit component
  bindings, human lease durations, application credential rotation and separate
  confirmed purge. Do not expose the server administrator, user/role
  management, Gremlin-Server administration or server configuration to
  project clients.
- The REST API is the initial query surface. Expose Gremlin only after
  validating its graph isolation, mutation permissions and script security in
  the pinned release. Application bindings inject the private REST endpoint,
  graph name and scoped credentials (for example
  `HUGEGRAPH_REST_URI`, `HUGEGRAPH_GREMLIN_URI`, `HUGEGRAPH_GRAPH`,
  `HUGEGRAPH_USERNAME`, `HUGEGRAPH_PASSWORD`); include the Gremlin endpoint only
  when enabled. The exact binding key set is fixed during the platform-contract
  step below.

## Access boundary to resolve before enabling the provider

HugeGraph's built-in auth supports graph-scoped targets with separate `READ`,
`WRITE`, `DELETE` and `EXECUTE` permissions. The documented `observer` default
role belongs to HStore graph spaces, so it cannot be assumed for this RocksDB
deployment. Build and verify graph-scoped reader and writer grants in the pinned
release before enabling either mode. In particular, `EXECUTE` covers Gremlin
execution and must not be treated as read-only. See the
[1.7 authentication API](https://hugegraph.apache.org/versions/1.7/docs/clients/restful-api/auth/),
[graph-space prerequisites](https://hugegraph.apache.org/versions/1.7/docs/clients/restful-api/graphspace/)
and [security guide](https://hugegraph.apache.org/docs/guides/security/).

1. Give each resource private access to only its graph, with separate
   platform-managed human and application identities. Route every client
   request through the access gateway; only the operator API and trusted relay
   may reach HugeGraph directly. Verify that a credential cannot enumerate or
   access another graph, another project's data, or server-level APIs.
   Graph names alone provide no isolation; the gateway must also deny graph
   listing, configuration and graph-management routes to project clients.
1. Map read-only grants to verified graph-scoped `READ` permissions. Prove
   enforcement for writes across every exposed surface, including REST write
   and batch APIs, Gremlin mutations and administrative endpoints. Test encoded
   paths and queries that use `POST`; reject by route and operation, not merely
   by HTTP method. Expose Gremlin to readers only if the pinned release and
   gateway can enforce read-only execution, including denial of script-based
   mutation and cross-graph access; otherwise reject reader Gremlin requests.
   A read-only grant must never become a full-access credential with an
   unrestricted network path.
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
1. Provide private REST client access first. Add Gremlin access only after the
   preceding graph isolation and script-security tests pass. Add
   HugeGraph-Hubble (or a platform browser console) only after proving the same
   scoped, revocable behavior through the lease relay; otherwise advertise
   browser access as unsupported.

The platform browser console uses the existing human lease gateway and bounded
REST routes. It previews graph pages and schema within one named graph; it does
not run Gremlin or expose the upstream Hubble server. Its launch, cookie,
revocation and cross-graph checks have focused gateway tests.

## Ordered implementation work

1. **Compatibility and capacity:** Validate the pinned HugeGraph release and
   container image in a disposable local fixture. Check image provenance,
   license and bundled notices, graph-scoped permissions, credential/session
   invalidation, published security advisories, the distribution's supported
   backup/restore method over RocksDB, health and metrics endpoints, and
   CPU/memory/disk headroom with all selected stores running. Record the
   implementation owner and resource budget in PLAN-038.
1. **Service foundation:** Add an opt-in Compose/Ansible service (`hugegraph`
   profile) with persistent RocksDB storage and configuration, distinct store
   and data/WAL paths per graph, private networking, bounded resources, health
   checks, pinned image, administrator secret management and an operator
   runbook. Enable authentication explicitly: it is disabled by default. No
   public HugeGraph REST/Gremlin port or Docker socket reaches applications or
   the Platform API.
1. **Platform contract:** Add `hugegraph` to the provider catalog, API schema,
   generated UI types, CLI and portal. Implement named graph
   create/inspect, reconciliation, explicit component bindings, credential
   issue/revoke/rotate, retirement and confirmed purge. Set per-graph security
   at creation before granting client access; fail closed if setup is
   incomplete.
1. **Data and security tests:** Verify vertex/edge create/update/delete,
   supported REST queries, schema and index management with representative
   fixtures. Test Gremlin only if it is enabled after separate security review.
   Exercise same-project and cross-project grants, reader/writer
   separation, system API denial, session fencing, service restart and
   partial provisioning retries. Test browser access if implemented.
1. **Operations:** Integrate service and per-resource health, bounded metrics,
   alerts, capacity admission and quota reporting. Record any monitoring-only
   quota limit explicitly; never call it a hard per-graph quota. Configure
   consistent encrypted off-host backups on the selected 12-hour schedule,
   including every graph's data, graph configuration and the authentication
   store, plus credential reconciliation inputs. Verify whether the selected
   export or snapshot method produces a consistent capture under concurrent
   writes; otherwise quiesce writes or stop the service for capture and record
   the interruption. Preserve the existing purge backup gate and verify that
   purge remains blocked without a verified backup in Phase 8. Verify actual
   off-host capture and readback in Phase 10.13.
1. **Acceptance and handoff:** Run offline checks, focused component tests and
   bounded deployed tests for the activated provider. Record revision, image
   digest, environment, evidence and limitations in PLAN-038. Off-host backup
   capture, restore, fresh credential issuance and application reconnection
   belong to
   [Phase 10 package 10.13](phase-10-anytime-leftovers.md#1013-verify-deployed-data-store-recovery-plan-027plan-033-follow-up).
   Compare HugeGraph with Neo4j Community and Apache AGE in
   [Phase 9 package 9.3](phase-9-store-measurement-and-comparison.md#93-graph)
   and as an activated deferred store in
   [package 9.5](phase-9-store-measurement-and-comparison.md#95-deferred-store-comparisons);
   those comparisons do not gate provider selection or the Phase 8 exit.

## Phase 8 exit for HugeGraph

Provisioning, isolation, read-only and read-write access, active revocation,
bindings, retained-data lifecycle, monitoring, bounded capacity, backup
configuration and the purge gate pass with recorded evidence. Any unsupported
capability is rejected and documented. Off-host backup capture and restore
verification belong to Phase 10.13; performance results belong to Phase 9.
