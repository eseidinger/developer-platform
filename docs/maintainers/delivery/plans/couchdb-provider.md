# CouchDB Provider — Next Data Store Increment

Status: selected on November 2, 2026; source implementation, disposable fixture
and bounded deployed access checks pass. The remaining Phase 8 acceptance checks
are open; off-host backup capture verification belongs to Phase 10.13. This
plan refines
[Phase 8 package 8.3](phase-8-deferred-data-stores.md#83-document-stores) and
[PLAN-033](../backlog.md#data-store-expansion-tasks). It does not select
MongoDB. Phase 7's unfinished acceptance and other Phase 8 packages remain
independent. The existing [store policies](data-store-expansion.md) apply.

The disposable CouchDB-only Compose fixture on November 2 verified the pinned
image, repeated provisioning, cross-database denial, document and Mango queries,
administrator-only index changes, service restart, recovered security and native
credential revocation. The relay's read-only and admin-index boundaries passed
focused local tests. The PostgreSQL provider constraint migration passed twice
in a disposable database.

The deployed check on November 2 installed source revision
`810e664e68bc2158cebdf47abece4b6645783ec0` on `node-01.eseidinger.de`
with CouchDB 3.5.3 pinned to image digest
`sha256:bed314d10cdf58c0fff63352db4c3f168df58a185a773c0e2295105375c5ef10`.
The selected capacity allocation was 4 GiB; the container limit was 768 MiB
memory and 0.5 CPU. CouchDB, PostgreSQL, the Platform API and the store relay
were healthy after deployment. API readiness returned 200 and Prometheus
reported `platform_native_couchdb_up=1`.

A temporary project and resource passed deployed provisioning, document writes,
reader reads, Mango queries, writer index creation, reader write and index
denial, system API and cross-database denial, and active reader revocation.
Both the test resource and project were retired. The first data-plane probe
returned a generic failure; a retry with bounded polling passed.
The deployment verification report is on the host at
`/opt/developer-platform/.runtime/couchdb-deployment-verification.json`.
The last verified backup capture was at 12:00 UTC, before this deployment.
A new backup start was rejected by the automatic approval review because it
would pause services and transfer platform data to the configured external S3
repository. CouchDB backup capture, off-host restore, application reconnection
and the remaining Phase 8 exit checks are therefore not claimed here. The
capture and restore checks are tracked in Phase 10.13.

The project-scoped browser console was deployed on November 2 from revision
`30dd17e2ca159bbb16b465600b55eb93f20cadbf`. It uses the same active human
lease and private relay as native clients, so reader and writer operations stay
within one named database. It is a platform document and Mango console, not
Fauxton. Forty focused provider, relay and console tests passed, as did the full
UI check and two browser scenarios covering reader and writer actions. On the
host, console enablement and all three packaged browser assets were confirmed;
CouchDB, the relay, PostgreSQL and the Platform API were healthy, and API
readiness returned 200. A browser session with a real deployed human CouchDB
lease had not yet been exercised at that point.

On November 10, the Ansible deployment of revision
`66a056d90b5be038e21c86b5a00aac267c8689a7+dirty` passed. The read-only
Phase 8 host smoke verified CouchDB container health, CPU/memory limits, private
ports, its named data volume and a native-up Prometheus metric of 1. See
[EV-73](../backlog.md#verification-register). Scoped deployed lifecycle remains
open. On November 10, the owner reported successful deployed browser checks
with separate reader and writer identities, reader write denial and access
denial after grant revocation; see [EV-74](../backlog.md#verification-register).

## Scope and decisions

- Add Apache CouchDB as an optional, shared Docker Compose service. Each named
  platform resource maps to a separate CouchDB database; application deployment
  never creates one implicitly. Keep PostgreSQL as the platform's own catalog
  and the reference for later JSONB comparisons.
- Use the official Apache CouchDB distribution under Apache License 2.0. Record
  the exact image digest, bundled component notices and supported client version
  before installation. Pin upgrades under the shared-store maintenance policy.
- Keep project data authoritative unless an application explicitly identifies a
  recoverable source. Replication is optional and is not a substitute for a
  protected, point-in-time backup: deletions and conflicts can propagate.
- Reuse project ownership, cross-project approval, explicit component bindings,
  human lease durations, application credential rotation and separate confirmed
  purge. Do not expose the server administrator, `_users`, `_replicator`,
  `_global_changes`, `_security`, or server configuration to project clients.

## Access boundary to resolve before enabling the provider

CouchDB database `members` can read **and write** ordinary documents; `admins`
can additionally manage design documents and database security. The native
`_security` object therefore does not implement the platform's read-only grant.
Mango index creation also requires administrator permission. See the
[CouchDB security reference](https://docs.couchdb.org/en/stable/api/database/security.html)
and
[Mango API reference](https://docs.couchdb.org/en/stable/api/database/find.html).

1. Give each resource private access to only its database, with separate
   platform-managed human and application identities. Route every client
   request, including read-write access, through the access gateway; only the
   operator API and trusted relay may reach CouchDB directly. Verify that a
   credential cannot enumerate or access another database, system database,
   server API or another project's data. Database names alone provide no
   isolation.
1. Design a fail-closed HTTP access gateway for read-only credentials. Allow
   only explicitly verified read operations, including any query endpoints that
   use `POST`; reject writes and administrative requests by route and operation,
   not merely by HTTP method. Test encoded paths, aliases, redirects, bulk APIs,
   attachments, design documents and changes feeds. A read-only grant must never
   become a CouchDB `member` credential with an unrestricted network path.
1. Fence both new and established access at lease expiry, revocation, rotation
   and retirement, including HTTP keep-alive and browser sessions. Keep service
   administrator credentials separate from resource bindings and redact them
   from API responses, logs and backups exposed to projects.
1. Let authorized resource writers manage supported Mango indexes through a
   narrowly scoped platform operation, executed with an operator-held credential
   against that database only. Validate allowed index definitions and audit
   changes; never issue database or server administrator credentials to writers.
   Reject unsupported design-document operations explicitly.
1. Provide private HTTP client access first. Add Fauxton or a platform browser
   console only after proving the same scoped, revocable behavior; otherwise
   advertise browser access as unsupported. Reject unsupported grant modes
   explicitly instead of silently upgrading permissions.

## Ordered implementation work

1. **Compatibility and capacity:** Validate the pinned CouchDB release and
   official image in a disposable local fixture. Check license notices, database
   security semantics, credential/session invalidation, published security
   advisories, backup method, health and metrics endpoints, and CPU/memory/disk
   headroom with all selected stores running. Record the implementation owner
   and resource budget in PLAN-033.
1. **Service foundation:** Add an opt-in Compose/Ansible service with persistent
   storage, private networking, bounded resources, health checks, pinned image,
   administrator secret management and an operator runbook. No public CouchDB
   port or Docker socket reaches applications or the Platform API.
1. **Platform contract:** Add `couchdb` to the provider catalog, API schema,
   generated UI types, CLI and portal. Implement named database create/inspect,
   reconciliation, explicit component bindings, credential issue/revoke/rotate,
   retirement and confirmed purge. Set database security at creation before
   granting client access; fail closed if setup is incomplete.
1. **Data and security tests:** Verify document create/update/delete, revision
   conflicts, authorized Mango index changes and schema evolution with
   representative JSON fixtures. Exercise same-project and cross-project grants,
   reader/writer separation, system API denial, session fencing, service restart
   and partial provisioning retries. Test browser access if implemented.
1. **Operations:** Integrate service and per-resource health, bounded metrics,
   alerts, capacity admission and quota reporting. Document any monitoring-only
   quota limit and compaction headroom; never call it a hard per-database quota.
   Configure consistent encrypted off-host backups on the selected 12-hour
   schedule, including data, design documents, security configuration and
   credential reconciliation inputs. Preserve the existing purge backup gate and
   verify that purge remains blocked without a verified backup in Phase 8.
   Verify actual off-host capture and readback in Phase 10.13.
1. **Acceptance and handoff:** Run offline checks, focused component tests and
   bounded deployed tests for the activated provider. Record revision, image
   digest, environment, evidence and limitations in PLAN-033. Off-host backup
   capture, restore, fresh credential issuance and application reconnection
   belong to
   [Phase 10 package 10.13](phase-10-anytime-leftovers.md#1013-verify-deployed-data-store-recovery-plan-027plan-033-follow-up).
   Compare CouchDB with PostgreSQL JSONB on versioned workloads in
   [Phase 9](phase-9-store-measurement-and-comparison.md#95-deferred-store-comparisons);
   that comparison does not gate provider selection or Phase 8 exit.

## Phase 8 exit for CouchDB

Provisioning, isolation, read-only and read-write access, active revocation,
bindings, retained-data lifecycle, monitoring, bounded capacity, backup
configuration and the purge gate pass with recorded evidence. Any unsupported
capability is rejected and documented. Off-host backup capture and restore
verification belong to Phase 10.13; performance results belong to Phase 9.
