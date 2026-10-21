# Data Store Expansion

Status: design and delivery plan, originally recorded October 17, 2026.
The earlier source assessment is historical: named PostgreSQL, RustFS,
OpenSearch, Qdrant and dedicated Neo4j Community providers are now implemented.
See the [Phase 7 checkpoint](phase-7-planned-data-stores.md) and
[current operator contract](../../../operators/data-stores.md) for delivered
behavior and scoped EV-67–72 evidence. Deferred Phase 8 providers and outstanding
acceptance remain planned; this documentation review ran no deployment or benchmark.

The [data store roadmap](../../../product/data-store-roadmap.md) is organized into
provider phases 7 and 8 plus a separate measurement phase 9:

| Phase | Scope | Tasks |
|---|---|---|
| [7 — Planned Data Stores](phase-7-planned-data-stores.md) | PostgreSQL baseline/integration, DuckDB/Parquet/S3, OpenSearch, AGE/Neo4j, pgvector/Qdrant | PLAN-026–030, PLAN-036 |
| [8 — Deferred Data Stores](phase-8-deferred-data-stores.md) | TimescaleDB, ClickHouse, Valkey, MongoDB/CouchDB | PLAN-031–033 |
| [9 — Data Store Measurement and Comparison](phase-9-store-measurement-and-comparison.md) | Eight performance dashboards and reproducible comparisons across selected stores | PLAN-037, with source evidence from PLAN-026–033 |

Phase 7 incorporates source roadmap phases 0–4; Phase 8 incorporates source
phases 5–7. Their provider acceptance covers functional integration, backup
safeguards and ordinary lifecycle checks. Deployed restore, rebuild and
application reconnection acceptance belongs to Phase 10 packages 10.11 and 10.13.
Quantitative measurements, comparisons and eight performance dashboards belong
to Phase 9 and do not gate provider selection or Phase 7/8 exit. Optional Phase 6
compute/service expansion is independent. [Phase 10 leftovers](phase-10-anytime-leftovers.md)
remains last, anytime and lowest priority. Phase 10 recovery work does not gate
provider selection or Phase 7/8 exit.

## Provisioning decision

**Owner-selected model (October 17, 2026):** Use shared services with isolated
project resources as the default for introduced stores. Provision project-owned
databases, buckets, indexes or collections as supported by each provider, with
scoped managed credentials, explicit application/component bindings, private
network access and quotas. Project resource names alone do not establish isolation:
verify authorization, revocation and cross-project denial for each selected
product/edition before offering the provider. Cross-project data access requires
an explicit authorized grant; shared hosting does not imply shared data access.

Operators own shared-service installation, upgrades, capacity and recovery.
Projects consume authorized logical resources and share the service's capacity
and failure domain. Document recovery impact across projects and enforce resource
bounds where the provider supports them; record unsupported controls explicitly.
Dedicated project instances require a separately justified expansion decision.
Selected data-store services remain running together under the capacity policy;
the owner may select them for experimentation or permanent use at will. This selects the provisioning
model; the resource lifecycle/binding decision below also applies to PostgreSQL.
Provider selection, detailed schemas and implementation remain open.

## Resource administration decision

**Owner-selected policy (October 17, 2026):** Project administrators create,
inspect, configure, retire and explicitly purge named resources owned by their
project, and manage resource grants and application/component bindings within
that project. Cross-project bindings follow the selected consumer request and
resource-owner approval workflow. Developers, viewers and application identities
do not acquire resource-administration powers through data/schema access.

Platform administrators have all project-administrator capabilities across all
projects, including resource-owner approvals and lifecycle/grant/binding actions.
They need no additional project-admin assignment. Preserve explicit confirmation,
retirement/access-cleanup prerequisites and audit requirements for purge; platform
administration does not bypass those safeguards. Record the acting administrator,
resource owner, consumer and scope for cross-project actions. Operators retain
shared-service installation, upgrades, capacity and recovery responsibilities.

Resource administration does not automatically issue native database or console
data credentials, including for platform administrators. Humans use explicit
resource-scoped read-only/read-write grants with the selected expiry policy;
applications use their explicit bindings. Verify role/project boundaries,
platform-admin reach across projects, cross-project approval and denial of
implicit data access under PLAN-026/036. This is the Phase 7 authorization plan,
not implementation or acceptance evidence.

## Shared-service placement decision

**Owner-selected placement (October 17, 2026):** Run shared data-store services
in Docker Compose on the current lab host, outside Kubernetes, alongside the
existing PostgreSQL persistence service. Version service definitions and
installation/configuration through the existing Compose/Ansible workflow, with
persistent storage, restart policy, health checks, private endpoints, explicit
resource limits and backup/monitoring integration. Selected services remain
running together under the agreed capacity policy.

Operators manage shared-service installation, startup, upgrades and retirement.
The Platform API manages logical named resources and bindings through scoped
provider administration interfaces; this placement does not require exposing the
Docker socket to project applications or the API. Kubernetes continues to host
application workloads and receive component-scoped secrets and network policies
for access to the private Compose store endpoints. Define endpoint discovery and
connectivity in the provider contract, without public store/admin ports by default.

This is a persistence placement decision, not activation of Phase 6's optional
Docker compute adapter or service extraction. Product selection, endpoint details,
volume sizing, implementation and operational acceptance remain open.

## Neo4j Community dedicated-instance decision

**Owner-selected exception (October 17, 2026; PLAN-029/036):** Integrate Neo4j
Community Edition using a dedicated Docker instance and persistent volume for
each named Neo4j resource, initially limited to one Neo4j resource per project.
Create the instance when requested and keep it running until explicitly retired;
retain its data until separately confirmed purge. Multiple applications/components
may share that resource through explicit bindings. Isolation is between instances,
not labels or query filters inside a shared Community database. This is a
Neo4j-specific exception to shared-service placement; other stores keep their
selected shared-service model.

Community provides one user database per instance and full access for all native
users, as documented in the
[edition comparison](https://neo4j.com/docs/cypher-manual/25/introduction/cypher-neo4j/).
Expose an explicit **full instance access only** capability for Neo4j Community.
Reject read-only grants/bindings as unsupported; never silently promote them.
Full access includes graph data and schema changes and the edition's available
native administration capabilities. This is an explicit exception to the common
read-only/read-write distinction and restriction on native administration within
that dedicated instance; it grants no platform, Docker-host or other-instance
administration. Other providers' grant semantics remain unchanged. Do not claim
separate permission boundaries between humans/components sharing this resource.

Preserve platform resource ownership and explicit grant/binding approval,
including owner approval for cross-project consumers. Issue separate human and
application identities. Retain 24-hour human credentials, 30-day application
rotation with at most one-hour overlap, and active-session closure at
expiry/revocation/retirement through both private native access and Neo4j Browser.
Before enabling the provider, verify that native user creation/password changes
and other full-access capabilities cannot bypass those platform controls. A
simple TCP tunnel or arbitrary-Cypher filtering is not sufficient evidence.

Use private per-instance endpoints, separate volumes and secrets, pinned images,
per-instance CPU/memory/storage accounting, health checks and monitoring. Add
capacity admission and operator-controlled instance provisioning/reconciliation;
this decision does not authorize a Docker socket in the API or relay. Extend
backup/recovery, retirement/purge and upgrade workflows to each instance.
Community's supported database dump is offline; scheduled backup interruptions
are accepted for this provider and must be documented and tested, including
security/configuration recovery and fresh access approval. See the
[backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/).
No commercial edition or license is selected.

**Source/local checkpoint (October 17, 2026):** Dedicated instances, explicit
full-access capability/read-only rejection, private Bolt and official Browser,
independent issued-secret verification, session fencing, instance capacity limits,
monitoring and stopped-volume recovery are implemented with disposable evidence.
The prior shared-instance incompatibility remains valid; this resource mapping
and access exception replace that deployment. Opt-in configuration readiness is
not deployed operational acceptance. See the
[compatibility record](../../../../infrastructure/persistence/compatibility/neo4j-2026-10-17.md)
and [operator workflow](../../../operators/data-stores.md#dedicated-neo4j-community-resources).

## Shared-store upgrade decision

**Owner-selected policy (October 17, 2026):** Shared data-store upgrades are
operator-triggered maintenance operations using pinned versions. Pin server
images by immutable digest and record compatible extension and console versions
in the versioned Compose/Ansible configuration. Do not automatically deploy newer
store releases or use floating tags as the deployed version contract.

Before upgrading, verify a recoverable backup under the selected policy, check
release-specific upgrade paths and compatibility with extensions, consoles,
provider adapters and application clients, and document the affected projects,
expected interruption and recovery procedure. Validate the procedure on a
disposable fixture before changing the shared service. A recovery plan must
account for on-disk/catalog migrations: switching back to an older image alone
is not a safe rollback unless explicitly supported and verified. Use restore or
rebuild where downgrade is unsupported, including AGE's selected projection rebuild.

Applications must tolerate the planned maintenance interruption and reconnect
or restart afterward. After upgrade, verify service health, resource data,
permissions, bindings, human/private/console access, credential lifecycle and
backup/telemetry integration. Record versions, checks and recovery outcome;
report partial failures without claiming successful acceptance. Preserve other
selected services unless the maintenance scope explicitly includes them.

Automatic application credential rotation remains independent of release
upgrades. Coordinate maintenance and rotation so retries preserve the selected
one-hour handover deadline and revocation rules. PLAN-026 establishes this
workflow for PostgreSQL; later provider packages extend it. These are planned
requirements, not a performed upgrade or recovery acceptance.

## Resource lifecycle and binding decision

**Owner-selected contract direction (October 17, 2026):** Manage storage as
independent named project resources, with separate create/read/update/retire/purge
operations and explicit application/component bindings. Support multiple resources
per project. Applications reference existing authorized resource IDs; deployment
does not implicitly create a default database or grant every component access.
Bindings define provider-supported permissions such as read-only or read/write,
and deliver scoped credentials and connection settings through managed secrets
only to the bound components. Verify binding revocation and credential rotation,
including removal from generated workloads and provider-side access denial.

Resource state and retention survive application redeployment/removal. Permanent
resource/data deletion is a separate explicit authorized action, following the
selected retirement/purge rules below.
Shared-service operator credentials never become application bindings. Cross-project
access remains an explicit authorized grant and must not be inferred from a
resource name or a shared service.

**Compatibility decision:** The owner accepts a clean setup and recreation of
applications/resources. No backward-compatible support for today's implicit
project PostgreSQL database, legacy resource declaration, automatic credential
injection, or existing application specifications is required for this redesign.
Do not add migration, compatibility aliases or dual old/new binding paths solely
to preserve existing setups. Include PostgreSQL in the new contract first and
recreate external application declarations against it for acceptance. Document
setup/reset steps and destructive effects before executing any recreation; this
planning decision performs no data deletion or environment reset. Exact API and
declaration shapes remain implementation/design work, not current capabilities.

## Cross-project resource sharing decision

**Owner-selected approval model (October 17, 2026):** A consumer-project
administrator requests access for a specific application/component to a named
resource owned by another project. An administrator of the resource-owning
project must approve the requested read-only or read-write access before the
platform creates usable scoped credentials and an explicit cross-project binding.
Read-write includes resource-scoped schema changes under the selected permission
policy. No pending, rejected or expired request grants data access.

Bind approval to stable resource, owner/consumer project, application/component
identities and the approved access mode. Recheck current authority and resource
state before provisioning or changing access. Permission increases or a different
resource/consumer require owner approval; an existing approval must not authorize
unrelated components or automatically propagate through another project. Keep
this storage grant separate from hosted application-to-application HTTP/OIDC
access grants and named human grants.

The owning project retains resource ownership, retention and deletion authority
and can revoke the grant. Disable further issuance/binding use immediately and
reconcile provider credential/session revocation and workload secret/network
cleanup; report pending or failed cleanup explicitly. Normal consumer redeploys
retain access only while identities, approved scope and grant remain valid.
Resource/project retirement follows the selected revoke-and-retain lifecycle.

Provide request, approve/reject, inspect and revoke flows in API/CLI/portal, with
an audit trail excluding secrets. Verify unauthorized approval, pending denial,
wrong resource/component, read-only enforcement, scope escalation, owner and
consumer retirement, active-session revocation and unaffected other consumers.
Requests for human access remain individual resource grants rather than inheriting
an application's approval. Detailed schemas and implementation remain open.

## Deletion and retirement decision

**Owner-selected policy (October 17, 2026):** Retain data by default and separate
access removal, retirement and permanent live-data purge. Apply these rules to
all named storage providers through the API, CLI and portal:

| Action | Required behavior |
|---|---|
| Remove an application/component | Revoke its resource bindings and credentials; retain resources/data and unrelated application bindings or human grants. |
| Remove a binding | Revoke that consumer's access; retain the resource, data, other bindings and human grants. |
| Retire a resource | Revoke every application binding and human grant, invalidate affected access/sessions and retain data plus recovery metadata. |
| Purge a resource | Permanently delete the retired resource's live data after a separate explicit authorized confirmation. |
| Retire a project | Retire its owned resources, revoke access and retain resource data for a separate purge. |

Require retirement and completed access cleanup before resource purge. Preview
the exact stable resource ID/name, affected provider objects, retained backup
copies and destructive effects before confirmation; revalidate the scope and
current authorization at execution. Pending cleanup or stale confirmation must
not bypass the gate. Make interrupted/retried retirement and purge operations
recoverable and report partial cleanup explicitly. Removing one consumer must
not invalidate another consumer's credentials for a still-active resource.

Purge of live data does not immediately erase historical backups. Existing copies
expire according to the agreed backup retention policy. Retain sufficient purge
metadata to prevent recovery from silently reactivating purged resources or old
grants; document the reconciliation procedure with provider recovery. Retiring
all resources does not automatically stop their shared service; selected shared
services remain running until explicit operator retirement or maintenance.

These are design decisions only. Resource/project retirement and purge perform
no live action as part of this plan amendment, and implementation/verification
remain open.

## Read-write and schema-management decision

**Owner-selected permissions (October 17, 2026):** Read-write access for both
applications and humans includes schema changes inside the granted named
resource. Permit supported creation, alteration and deletion of application
schemas, tables, indexes, constraints and sequences, alongside data operations.
Applications may perform migrations during startup with their read-write binding;
a separate migration identity/job is optional, not mandatory.

Implement PostgreSQL object ownership/membership through resource-scoped roles
so authorized application and human writers can manage existing and newly created
objects, including each other's objects within the same resource. Do not equate
schema-management access with shared-server administration: it grants no
superuser, global role management, extension installation/upgrade, access to other
resources, or permission to drop/purge the named resource itself. Platform-owned
extension catalogs and control-plane objects remain protected. Resource purge
continues to use the separately authorized lifecycle workflow.

Read-only identities must be unable to change data or schema. Permission downgrade
and revocation must remove both data and schema authority, end affected sessions
and address object ownership or role memberships that could otherwise preserve
write access. Verify future-object ownership/default privileges and cross-writer
DDL, rather than granting CREATE alone and assuming it permits ALTER/DROP.
Map the same intended access level to each provider's supported schema/index
operations; reject unsupported combinations rather than granting service-wide
administration. Exact role mappings and implementation remain open.

## Human access to named resources

**Owner-requested extension (October 17, 2026):** Extend the human PostgreSQL
access model to independently named project resources and add explicit read-only
and read-write grants. This is Phase 7 implementation scope; the current API
still exposes project-scoped read-only PostgreSQL access only. Apply the generic
grant model to each introduced store using its supported permission capabilities.

Identify grants by stable resource ID and named OIDC human identity, with an
explicit access mode. A human may have read-only access to one resource and
read-write access to another in the same project. Display resource names for
selection while keeping grants attached to stable IDs across renames. Project
membership or application bindings do not implicitly grant human data access.
An authorized project access administrator grants, changes and revokes access;
humans inspect only their permitted resources and obtain their own credentials.

For PostgreSQL, scope permissions to the selected database and its managed
application objects. Read-only permits connection, schema usage and reads.
Read-write permits data changes, sequence use and application-schema DDL under
the [selected schema-management policy](#read-write-and-schema-management-decision).
Keep server/global administration, platform-owned extension objects and resource
purge separate. Configure existing/future object ownership and privileges for
all supported application/human writers; verify AGE/pgvector permissions against
their actual objects and provider semantics.

Use separate human credentials for each resource grant, never the application or
shared-service administrator secret. Extend the API, CLI and portal with resource
selection, access mode, grant inspection/change/revocation, private connection
instructions, credential issuance/rotation and SSH-key handling where applicable.
Map issuance/expiry to supported provider mechanisms and expose limitations
explicitly. Fail unsupported resource/access-mode requests before side effects;
do not silently broaden permissions. Downgrading read-write to read-only and
revoking access must remove provider privileges and invalidate affected sessions
or credentials so already connected clients cannot retain data-write or schema authority.

Audit grant creation, permission changes, credential lifecycle and revocation
without recording credential values or query content. Verify two named resources
with different permissions for one human, multiple humans, existing/future objects,
read-only write/DDL denial, read-write data and cross-writer schema operations,
unrelated-resource/project
denial, application/human separation, downgrade/revocation of active sessions,
resource rename/retirement and restoration of the intended grants after recovery.
Retiring one grant/resource must not revoke another resource's access by mistake.

This redesign uses the already accepted clean setup; no legacy grant migration
or backward-compatible project-only routes are required. Preserve current guides
as descriptions of implemented behavior until the replacement is delivered.
Exact schemas, provider mappings, implementation and deployed acceptance remain
open.

## Human credential expiry decision

**Owner-selected policy (October 17, 2026):** Human credentials for named
resources expire after **24 hours by default**, measured from issuance or renewal.
Keep the durable resource grant separate from issued credential validity: an
authorized human can obtain a fresh time-limited credential only
while the resource and grant remain active and the current permission scope
still permits it. Recheck the authenticated human, resource, grant and access mode
at every issuance/renewal. A revoked or downgraded grant must not renew old powers.
Application/component credentials follow the separate
[automatic rotation policy](#application-credential-rotation-decision).

Expose issuance time, expiry and renewal instructions in API/CLI/portal and the
private/console connection workflows. Do not expose credential values in logs,
URLs or shared console profiles. Use provider-enforced expiration or a verified
resource-scoped credential lease/revocation mechanism; record actual enforcement,
outage behavior and precision. A timestamp shown by the portal alone does not
enforce expiration, and lack of native provider support must not silently produce
persistent credentials. Close active connections authenticated with a credential
when that credential expires, including native database sessions, tunnels and
console backend sessions. Require renewal and reconnection to continue; renewing
a credential must not silently extend sessions authenticated with the old one.
Warn users about expiry and interrupted work before the deadline.
Early renewal issues a new credential with its own 24-hour default validity.
The old credential and its existing connections remain valid until the old
credential's original expiry; renewal does not extend that deadline. Revocation,
retirement or permission downgrade still overrides this overlap immediately.
Providers must support independently expiring credential generations, directly
or through a verified lease mechanism, rather than resetting a single expiry
for both generations.

Verify expired-credential connection denial through both private and console
paths, authorized renewal, denial after revocation/retirement/downgrade, and
cleanup after interrupted issuance/renewal, including enforcement of the 24-hour
default and closure of active connections at credential expiry through both
access paths. Verify early-renewal overlap, independent expiry of old and new
credentials, and revocation/downgrade across all outstanding generations. These
are planned requirements, not implemented behavior.

## Application credential rotation decision

**Owner-selected policy (October 17, 2026):** Automatically rotate managed
application/component credentials for named-resource bindings **every 30 days**.
Applications must
tolerate a controlled restart to pick up new credentials; live credential reload
is optional. The platform handles rotation, managed-secret updates and affected
workload restarts without users copying secrets or changing configuration.
Brief interruption during restart is acceptable; uninterrupted service is not a
requirement of this policy.

Issue a new resource-scoped credential generation after checking the active
resource, binding and approved permission scope. Update managed secrets only for
the bound components, restart affected workloads and verify readiness plus access
using the new credential, then retire the old generation promptly. Allow at most
**one hour of overlap**, measured from issuance of the replacement credential.
Revoke the old generation and close its remaining connections by that deadline,
even if rollout has failed; report the failure and required recovery action.
Retries must not reset or extend the original overlap deadline. Preserve
unrelated bindings, human grants and shared store availability; restart consuming workloads, not the shared store service.
Revocation, retirement and permission downgrade override rotation overlap and
must remove obsolete access across every credential generation.

Reconcile interrupted rotation and partial rollouts without leaking credentials
or leaving old generations valid indefinitely. Expose rotation status, failures
and required operator action without secret values. Define bounded failure
and retry behavior during implementation; failed rollout must not be
reported as successful rotation. Verify secret propagation, restart/readiness,
new-generation access, old-generation rejection after handover, enforcement of
the one-hour deadline during failed or interrupted rollouts, partial-failure recovery and isolation of
unaffected consumers.

Schedule each credential generation for automatic rotation 30 days after issuance;
verify scheduling, retries and the one-hour overlap deadline across controller
restarts. Human credentials retain their separate 24-hour validity policy.
These are Phase 7 requirements, not implemented behavior.

## Private and browser-console access decision

**Owner-requested scope (October 17, 2026; PLAN-036):** Deliver both private
native-client access and browser-console access for named resources in Phase 7.
Neither replaces the other. Both use the same current human grant and its
supported mode, including the selected resource-scoped schema powers. The
[Neo4j Community exception](#neo4j-community-dedicated-instance-decision) exposes
full instance access only and rejects read-only grants; other providers retain
their read-only/read-write distinction.
Build the common access contract with PostgreSQL in package 7.1, then implement
the provider-specific adapters as packages 7.2–7.5 introduce stores. No new access
path or console is delivered by this planning amendment.

### Private access

Extend the existing SSH-bastion approach with authorized connection instructions
and destinations for each named resource/provider. Supply the grantee's separate
resource credential for use with native SQL, S3, search, graph or vector clients.
Keep raw store ports private; tunnel authorization and backend credentials must
both be valid. An SSH destination to a shared server does not itself isolate
its databases/buckets/collections: enforce resource permissions at the provider.
Expose discovery/instructions and key/credential lifecycle through API/CLI/portal.

### Browser-console access

Provide a resource-page console launcher with an authenticated HTTPS route to
an operator-deployed console, keeping its backend connection private. Integrate
the existing OIDC/access boundary and use native SSO where the selected console
supports it; otherwise document the separate console login using the human's
scoped resource credential. Do not imply that a platform login automatically
creates an authorized backend session. Console access must not use shared-service
administrator or application credentials, or silently widen a resource grant.

| Provider | Console implementation direction |
|---|---|
| PostgreSQL / pgvector | pgAdmin web access with separate human connections and database-enforced resource permissions. |
| Apache AGE | SQL/Cypher access through the PostgreSQL console with verified session setup; a dedicated graph visualization tool is optional. |
| S3-compatible storage | Integrate the official RustFS console with resource-scoped human access. Verify pinned-release login, permission boundaries, expiry and session revocation. |
| OpenSearch | OpenSearch Dashboards with provider-side index permissions mapped to the named resource. |
| Neo4j | Neo4j Browser for a dedicated Community instance per resource, initially one per project; explicit full access only, with unsupported read-only grants rejected. See the [dedicated-instance decision](#neo4j-community-dedicated-instance-decision). |
| Qdrant | Qdrant Web UI with the selected deployment's resource-scoped authorization. |

Choose and pin supported console releases, record their licenses, and integrate
with operator Docker Compose/Ansible deployment, health, resource budgets and
necessary configuration backup. Use backend authorization, not filtered console
navigation, to enforce scope. Exclude operator/global administration capabilities
from project access. Support required HTTP/WebSocket connection paths without
opening unrestricted backend destinations. Keep credentials out of launch URLs,
query parameters, audit logs and shared connection profiles; review each console's
credential persistence behavior during integration.

### Common access acceptance

Verify both paths with multiple named resources/projects and read-only/read-write
humans: reads, permitted data/schema writes, denied writes/DDL for read-only users,
resource/project isolation, grant downgrade, credential/key rotation, revocation,
retirement and reconnect behavior. Terminate affected database and console
sessions, including long-lived connections where applicable, so revocation or
permission downgrade cannot preserve prior access. Test an already open console,
its backend API and direct tunneled requests; hiding a button is insufficient.
A console restart must not restore revoked grants or share one user's saved
credentials with another. Record provider-specific capability limitations and
resolve them before claiming that access path is operationally supported.

Exact route/API schemas, console release pins, SSO/session mechanisms and
provider mappings remain engineering work. Existing private PostgreSQL access
continues to describe current behavior until the clean-setup redesign is delivered.

## PostgreSQL extension compatibility check

**Checked October 17, 2026:** The current server declaration in
[`infrastructure/persistence/compose.yaml`](../../../../infrastructure/persistence/compose.yaml) is
`postgres:18.6-trixie`. A local disposable, network-disabled fixture built and
ran the following stack together on PostgreSQL 18.6, Linux x86-64:

| Extension | Tested release tag | Exact source commit |
|---|---|---|
| pgvector 0.8.7 | `v0.8.7` | `f37c13f68b57d2c3472b2214fbcff699d6d34876` |
| Apache AGE 1.8.0 | `PG18/v1.8.0-rc0` | `e43dc1a12b78fba4acef9835b2b10379b8d243b4` |
| TimescaleDB 2.30.2 | `2.30.2` | `b0977bf2d3a5014ee870247be09bc19d3e9f7a5f` |

All eight extension subsets, in forward and reverse creation order (16 database
cases), passed basic relational/vector HNSW/graph/time-series query smoke checks
as a non-superuser database owner. Both `timescaledb,age` and `age,timescaledb`
preload orders started and queried successfully, including persisted data after
restart. A plain database had none of these extensions registered even though
their libraries were installed/preloaded. Vector and time-series queries also
worked after a combined logical dump/restore with TimescaleDB's pre/post-restore
hooks.

Two AGE limitations were reproduced:

- **Session loading:** an ordinary role's `LOAD 'age'` fails when AGE is not
  globally preloaded. Preloading AGE, granting `ag_catalog` usage and setting
  the session search path allowed the tested non-superuser graph operations.
  Do not grant application superuser privileges as a workaround.
- **Logical restore:** plain `pg_restore` completed, but Cypher then failed with
  `graph with oid ... does not exist`. The graph catalog retained stale namespace
  OIDs. This happened in both the combined and AGE-only databases; it is not
  evidence of an extension coexistence conflict. The fixture-only catalog repair
  described in [upstream issue #2503](https://github.com/apache/age/issues/2503)
  restored graph queries and the two-node count. This is a tested diagnostic
  workaround, not an approved general-purpose production recovery procedure.
  Phase 10 package 10.13 must provide validated AGE recovery or rebuild before
  claiming operational recovery acceptance. A separate server would not by itself fix
  this AGE-only logical-restore defect.

### Apache AGE restore diagnosis

The observed failure is stale graph-to-schema metadata after logical restore.
AGE stores the graph schema reference both as `ag_graph.namespace`
(`regnamespace`, resolved by schema name during restore) and as the numeric
`ag_graph.graphid` OID. Label metadata in `ag_label.graph` references that graph
ID. PostgreSQL assigned new schema OIDs in the target database, but the numeric
AGE graph IDs retained their source values:

| Restored fixture | AGE graph ID | Actual restored schema OID | Match |
|---|---|---|---|
| AGE + vector + TimescaleDB | 24004 | 32615 | No |
| AGE only | 17400 | 33690 | No |

The logical restore command succeeded; subsequent Cypher queries failed. The
fixture repair updated label references and graph IDs together, temporarily
removing and then restoring the graph foreign-key constraint in one transaction.
Cypher queries then returned the expected two-node count in both fixtures.
The exact diagnostic/repair SQL and test sequence are retained in the
[check script](../../../../infrastructure/persistence/compatibility/check.sh); observed errors,
OID values and repair results are in the
[fixture output](../../../../infrastructure/persistence/compatibility/results-2026-10-17.txt).
These observations match the mechanism reported in
[upstream #2503](https://github.com/apache/age/issues/2503).

A later [source-projection recovery fixture](../../../../infrastructure/persistence/compatibility/projection-rebuild-2026-10-17.md)
now reproduces this failure and rebuilds two graphs from protected source snapshots
using normal AGE graph/label APIs. Ordinary SQL, pgvector data and declared graph
indexes survive. No manual OID catalog repair is used. This is local implementation
evidence; deployed recovery/reconnection and RPO/RTO acceptance remain open.

### Apache AGE rebuild policy

**Owner-selected policy (October 17, 2026):** Initially use AGE graphs only as
rebuildable projections of protected authoritative source data. AGE must not be
the sole copy of unique domain data. Keep versioned source references, graph
mapping/schema definitions and reproducible loaders with the recovery inventory;
protect them under the selected backup policy.

Read-write application bindings and human grants retain their selected data and
schema permissions. Any durable graph change must also be represented in the
protected source data and projection definitions; direct AGE-only edits are not
protected authoritative state and may be lost on rebuild. Explain this in the
resource documentation and access workflows. This policy does not restrict
Neo4j or other stores to derived data automatically.

Recover by creating fresh AGE graphs and loading vertices, edges and properties
from the protected sources, recreating indexes/constraints and reconciling scoped
ownership/permissions plus current bindings. Verify representative multi-graph
rebuilds, source-to-graph completeness, Cypher reads/writes and application
reconnection, including rebuild time within the four-hour service recovery target
and source recovery within the 24-hour RPO. Do not accept a working two-node
catalog repair or successful `pg_restore` as this evidence. Unique authoritative
AGE storage requires a separate future decision and validated backup/restore
procedure; it is outside the initial implementation policy.

**Recovery follow-up for PLAN-026/029:** Do not equate a successful dump/restore
exit code with recovered graph functionality. Implement and validate the
owner-selected rebuild route from protected authoritative data under the
[AGE rebuild policy](#apache-age-rebuild-policy). Upstream fixes and reviewed
repair procedures may be investigated separately; they do not replace the
selected initial rebuild requirement. Check Cypher reads/writes, vertices/edges/properties,
multiple graphs and labels, constraints/indexes/sequences, ownership and scoped
permissions, and fresh/pooled application connections after recovery. Record
elapsed recovery time and data completeness against the selected recovery policy.
The current two-node fixture verifies the diagnostic workaround only; it does
not validate arbitrary graphs or production recovery. A separate AGE server
would still need this recovery work. Physical backup/restore was not tested.

The separate session-loading finding is configuration-related: application roles
must remain non-superuser. The tested working setup preloaded AGE server-side,
granted `USAGE` on `ag_catalog` and set the session search path. Application pool
configuration and least-privilege binding behavior still need implementation
and verification.

**Implementation consequence:** one shared PostgreSQL 18 instance with compatible
extension packages is a viable tested starting point. Enable extensions per named
database resource rather than enabling every extension in every database. AGE
needs an explicit session/preload policy; TimescaleDB needs server preloading if
selected later in Phase 8. No instance split was required by these smoke checks.
The existing plain production image does not yet contain these packages and was
not replaced. No live platform data, services, or deployment configuration changed.

The fixture is intentionally limited: it does not establish all workloads,
concurrency/planner interactions, large-data performance, extension upgrades,
least-privilege read/write binding matrices, physical recovery, RPO/RTO targets
or full platform acceptance. TimescaleDB's default source build includes TSL;
the deployment edition/license choice remains open. Its source build needed ICU
headers in addition to the other build dependencies.

Reproduction uses the pinned-base/source
[Dockerfile](../../../../infrastructure/persistence/compatibility/Dockerfile) and
[check script](../../../../infrastructure/persistence/compatibility/check.sh):

```bash
docker build -t developer-platform-postgres-compat:20261017 infrastructure/persistence/compatibility
docker run --rm --network none --user postgres --memory 2g --cpus 2 \
  --tmpfs /tmp:rw,size=768m,mode=1777 \
  --mount "type=bind,src=$PWD/infrastructure/persistence/compatibility,dst=/check,readonly" \
  --entrypoint bash developer-platform-postgres-compat:20261017 /check/check.sh
```

The harness prints `LIMITATION` for the specifically reproduced AGE failures;
a zero exit means the smoke matrix completed, not that these limitations passed.
It rejects unexpected errors. Retained fixture output is linked from EV-48 in
the backlog. Upstream references: [pgvector 0.8.7](https://github.com/pgvector/pgvector/tree/v0.8.7),
[AGE PG18 release](https://github.com/apache/age/releases/tag/PG18%2Fv1.8.0-rc0),
and [TimescaleDB 2.30.2](https://github.com/timescale/timescaledb/releases/tag/2.30.2).

## Object-storage selection priority

**Owner-selected priority (October 17, 2026):** Optimize initial object storage
for straightforward operation on the current single-host lab. The comparison of RustFS,
Garage and MinIO covers reproducible installation/configuration, supported S3
operations used by ODIP/DuckDB, project bucket/credential isolation and binding
permissions, versioning/checksums, resource use, monitoring, upgrade/rollback and
backup/recovery effort. Verify current distribution, license, maintenance and
supported deployment mode before selecting a product. Favor the simplest
supported topology that meets those acceptance criteria; future distributed or
multi-host operation is not a requirement for initial selection. Single-host
failure is addressed through the agreed recovery policy rather than an implied
high-availability claim. Placement is Docker Compose under the decision above;
RustFS is the owner-selected product, with its official console for browser
access. Pin a verified server/image and compatible console release during
implementation. Detailed configuration, release pins and acceptance remain open;
this selection does not deploy the service.

### Object-store comparison (October 17, 2026)

This is a documentation-based comparison for the owner's single-host Docker,
private/native plus browser-console access and managed-credential policies.
It is not a deployed compatibility, performance or recovery test. Product
selection is now RustFS by owner decision; this comparison is not operational
acceptance.

| Area | RustFS | Garage | MinIO Community |
| --- | --- | --- | --- |
| Installation | Official Docker image and documented single-node persistent-volume setup. | Official Docker image, self-contained service, documented single-node mode; persist both metadata and object data. | Source-only distribution requires maintaining our own build/image; old binaries are unmaintained. |
| License | Server and official console: Apache-2.0. | Server: AGPLv3; any added browser tool needs its own release/license review. | Community server: AGPLv3. AIStor is a separate product/license. |
| Resource access | IAM policies, users, service-account keys and OIDC/STS mechanisms provide a close conceptual fit; verify named-bucket permissions in the pinned release. | Per-access-key/per-bucket permissions fit basic resource read/write isolation; AWS IAM/bucket policies are not implemented. | Existing S3/IAM capabilities are relevant, but upstream maintenance status outweighs feature breadth for a new deployment. |
| Browser access | Official console includes object browsing and identity/policy/key management. Verify scoped non-admin login, expiry and inability to self-escalate. | Plan a separate S3 browser/console integration; assess its user isolation and avoid exposing cluster admin tokens. | README documents an embedded object browser; do not assume historical full administration UI features remain. |
| Object protection | Versioning documented; pinned CLI capabilities require checking. | No object versioning or Object Lock in the current compatibility matrix; lifecycle support is partial. | Historically broad S3 functionality; selecting an archived release transfers ongoing maintenance responsibility to us. |
| Telemetry | OTLP metrics/traces/logs; route into existing Alloy/Prometheus/Tempo/Loki, verifying collector compatibility. | Prometheus metrics and OpenTelemetry traces documented. | Existing monitoring ecosystem, with no ongoing upstream server maintenance. |
| Main tradeoff | Best documented fit for the combined console/access requirements, with a newer release lineage requiring careful recovery and upgrade verification. | Lightweight self-hosting focus and longer operating history, with narrower S3 features and additional console/access integration. | Archived and explicitly unmaintained upstream; highest maintenance burden for this new deployment. |

**Owner-selected product (October 17, 2026): RustFS**, following the comparison
recommendation, with the official RustFS console. Use one shared, continuously
running Docker Compose service with isolated named project buckets and explicit
application/component bindings. Implement private native S3 access and protected
HTTPS console access under the common grant and credential policies. Garage remains a reasonable alternative when lightweight core
storage matters more than integrated console/IAM features and object versioning.
Do not select archived MinIO Community as the default for a new managed service.
This is an engineering judgment based on the requirements and sources, not a
measured resource-use or reliability ranking. RustFS's release page currently
lists 1.0.2 (October 16, 2026); do not infer deployed-release support from moving
main-branch documentation, or deploy floating `latest` tags.

**Credential-policy fit:** RustFS documents independently managed service-account
keys with explicit expiry, which could support human 24-hour credentials and
application 30-day rotation with one-hour overlap. Its STS credentials are limited
to 12 hours, so native STS alone does not meet the selected 24-hour human policy.
Verify console login with the chosen credential type, or integrate a verified
lease/session layer; OIDC login alone is not proof of the selected expiry and
revocation behavior. For Garage, implement and verify access-key generation,
rotation and expiry enforcement through the provider adapter; expiring admin API
tokens do not demonstrate expiry of S3 data credentials. For every candidate,
verify denial of subsequent S3 requests, browser-session closure and cancellation
or bounding of in-flight transfers at expiry; persistent HTTP connections are
not equivalent to database authentication sessions.

**Recovery and operations:** All candidates still need the selected encrypted
off-host backup schedule and restore verification, including objects, versions
where supported, metadata, permissions and platform binding state. Versioning or
replication alone is not the backup plan. Validate consistency during capture,
checksums, recovery time, upgrade/rollback and combined host capacity. No
candidate's RAM/CPU footprint or RPO/RTO was measured in this comparison.

Primary sources checked:
[RustFS deployment](https://github.com/rustfs/docs.rustfs.com/blob/main/content/en/installation/container/docker.md),
[server/license](https://github.com/rustfs/rustfs),
[releases](https://github.com/rustfs/rustfs/releases),
[console/license](https://github.com/rustfs/console),
[IAM](https://docs.rustfs.com/en/security-compliance/iam),
[service accounts and STS](https://docs.rustfs.com/en/security-compliance/iam/sts),
[versioning](https://docs.rustfs.com/en/administration/data/object/versioning),
[telemetry](https://docs.rustfs.com/en/operations/observability);
[Garage quick start](https://garagehq.deuxfleurs.fr/documentation/quick-start/),
[features](https://garagehq.deuxfleurs.fr/documentation/reference-manual/features/),
[S3 compatibility](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/),
[admin tokens](https://garagehq.deuxfleurs.fr/documentation/reference-manual/admin-api/),
[project/license/history](https://github.com/deuxfleurs-org/garage);
[MinIO archive notice, distribution and browser](https://github.com/minio/minio).

## Backup and recovery decision

**Owner-selected policy (October 17, 2026):** Extend the existing platform backup
policy to authoritative data in every introduced store: backups every 12 hours,
retaining 14 daily, 8 weekly and 6 monthly recovery points, with encrypted
copies off-host, a 24-hour RPO and a four-hour RTO. Reuse the existing external
backup repository and credential-management approach where technically suitable;
the new single-host object store cannot be the only backup destination for data
on that host. Validate consistency, version/checksum preservation, independent
backup access before Phase 7/8 acceptance. Validate provider-supported restore
and rebuild methods in Phase 10 packages 10.11 and 10.13.

For derived search, graph and vector indexes, retain protected configuration,
source dataset/version references and reproducible rebuild procedures. An index
is rebuildable only if its authoritative data and required artifacts are
recoverable; otherwise treat its unique data as authoritative and back it up.
Include rebuild and application reconnection time in the four-hour service
recovery target. Coordinate recovery points across database state, versioned
objects and projections so restored references resolve consistently.

Operators own backup execution, monitoring, credentials and shared-service
recovery; application owners verify domain data and rebuild correctness. Record
measured loss/recovery time and named owners for each provider under the existing
lab validation policy. These targets are selected policy, not evidence that new
stores meet them. Document exceptions for owner decision rather than silently
weakening the policy. See the [backup workflow](../../../operators/backup-and-recovery.md)
and [confirmed schedule/retention](../../../../operations/backup/README.md).

## Capacity decision

**Owner-selected policy (October 17, 2026; amended):** Keep selected data-store
services running persistently alongside PostgreSQL, applications and platform
services. This supersedes the earlier one-additional-specialized-store-at-a-time
experiment policy. Adding another selected store does not stop an existing one;
experiment completion, idle periods or absence of current bindings do not
implicitly deactivate a selected shared service. Normal maintenance, recovery
and explicit operator-directed retirement remain lifecycle operations.

Measure the combined existing-host budget and preserve documented operating
reserves. Before adding each service, set explicit CPU, memory and storage limits
and account for simultaneous startup/steady-state peaks, rebuild and backup/recovery
work, plus the expanded 100% tracing/24-hour retention workload. Assign bounded
shared-service and project allocations, with provider-enforced quotas where
supported and documented admission/monitoring controls otherwise. Do not infer
available capacity from the source roadmap's VM figures.

If the accumulated selected services cannot coexist within the measured budget,
review a concrete capacity increase before adding the next one. Do not substitute
rotating services or automatic shutdown for sufficient capacity. Exact budgets
and upgrade sizing remain engineering work; this policy allocates no resources
and claims no capacity acceptance.

## Storage quota exhaustion decision

**Owner-selected policy (October 17, 2026):** At a named resource's storage
quota, reject operations that increase its charged storage usage where the
provider supports enforcement. Preserve reads and authorized cleanup operations
where technically possible, and alert administrators with resource scope,
usage/limit and an actionable explanation through the platform's operational
surfaces. Do not automatically expand quotas, delete retained data or stop the
shared service as the quota response.

Quota increases require explicit approval by an authorized administrator after
checking project/shared-service allocations, physical capacity and operating
reserves. Resource administration must not bypass operator-owned capacity bounds.
Account for retained object versions, indexes and provider overhead in the
provider's documented quota model; object deletion may retain versions and need
not immediately release charged space. Keep confirmed resource purge separate
from ordinary cleanup and preserve the selected backup/retention policy.

Distinguish resource quota exhaustion from shared-volume disk exhaustion. Reserve
headroom for provider metadata, compaction, cleanup and recovery; reads/cleanup
availability at a resource quota is an intended behavior, not a guarantee that a
physically full volume remains operable. Where precise per-resource enforcement
or selective write denial is unsupported, explicitly document the limitation,
use admission/monitoring controls and report their coverage and overshoot risk.
Do not label monitoring-only protection as a hard provider quota.

PLAN-026 and subsequent provider adapters must verify growth denial, reads and
cleanup, quota alerts, authorized increases, retained-version accounting where
applicable and isolation of unaffected resources. Record provider-specific
behavior and limitations rather than claiming uniform enforcement. Exact numeric
allocations remain engineering work; this decision does not implement quotas.

## Store selection decision

**Owner-selected policy (October 17, 2026):** Data stores may be selected at will.
No benchmark success criteria, minimum improvement, proof that PostgreSQL is
insufficient, domain-need justification or measured-benefit threshold gates
selection, adoption or permanent use. This supersedes earlier roadmap language
requiring demonstrated value or a workload trigger. Learning and personal
preference are sufficient reasons to choose a store. Phase 8 remains deferred
for scheduling purposes and can be activated whenever the owner chooses.

Comparisons and realistic workload measurements remain useful learning and
operational documentation under [Phase 9](phase-9-store-measurement-and-comparison.md);
their results do not approve or reject a technology.
Record the chosen store and any observations without requiring it to outperform
the baseline. The already selected shared-service provisioning, explicit bindings,
isolation, backup/recovery and capacity policies still govern implementation and
operation. Operational verification is distinct from benchmark success; the
choice itself requires no success criteria.

## Ownership and common acceptance

The platform owns generic resource provisioning, secrets and bindings, network
policy, lifecycle, backups/recovery, monitoring, quotas, and retirement. ODIP owns
the shared experiment framework, dataset versions, adapters, and analytical/search
comparisons. VEF owns dependency/constraint semantics; Energy and Bot Social own
their domain scenarios. Bot Social Core (bots, profiles, posts, relationships and
reproducible synthetic load) is an external prerequisite for its experiments.
No application-specific profile or benchmark logic belongs in the Platform API.

Extend the current Kubernetes provider and Python API through a shared resource
specification with store-specific provider schemas. PostgreSQL remains the
reference and initially authoritative store. Search, graph, and vector indexes
should be rebuildable projections where appropriate; document each source of
truth and evaluate a transactional outbox before adding event infrastructure.
Kafka or NATS JetStream requires evidence for replay, independent consumers,
decoupling, or event volume.

Every activated provider must demonstrate provisioning/reconciliation, retry and
restart behavior, scoped access and revocation, managed secret rotation/redaction,
network isolation, bounded capacity, health/alerts, upgrade/rollback, and retirement
with explicit retention/deletion policy. Record working backups in Phase 7/8;
measure authoritative-data recovery and demonstrate derived-index rebuild and
retained-configuration reconciliation in Phase 10. Document supported versions,
license, maturity, operating model,
and recovery ownership before selection. Use the existing lab under its recorded
validation policy, with bounded impact and recovery steps; do not provision another
test environment. Keep selected shared stores running with bounded resource
allocations and measure their combined capacity before adding services. Recheck host capacity;
the source roadmap's VM figures are not verified sizing evidence.

The [Phase 9 measurement plan](phase-9-store-measurement-and-comparison.md)
records versioned data, reproducible workloads and environments, equivalent
results, quantitative performance, resource use and operating cost. Isolated
performance comparisons may use the local workstation. No result or success
threshold gates adoption or permanent use.

Execution and evidence: [PLAN-026–033, PLAN-036 and PLAN-037](../backlog.md#data-store-expansion-tasks).
Assign named platform and external experiment owners before each phase starts.

