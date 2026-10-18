# Phase 7 — Planned Data Stores

Status: implementation in progress as of October 18, 2026. The scoped 7.1
PostgreSQL acceptance gate has local and deployed evidence, including active
pgAdmin Query Tool session fencing and verified-backup-gated purge (EV-52–67).
The four shared-store providers have combined deterministic deployed acceptance
through test personas (EV-68). Deployed AGE/pgvector selection and scoped queries
have a separate disposable check (EV-69). An October 18 local rerun of native,
analytics and official browser fixtures passed (EV-70). A deployed synthetic
application flow now verifies artifact metadata/outbox and search updates (EV-71).
Domain comparisons and quantitative
performance verification are now [Phase 9](phase-9-store-measurement-and-comparison.md);
deployed store restore and rebuild acceptance are
[Phase 10 package 10.13](phase-10-anytime-leftovers.md#1013-verify-deployed-data-store-recovery-plan-027plan-033-follow-up).
Elapsed-time behavior and operator/browser review remain open under their
recorded package scopes.

**Current evidence note, October 18:** EV-72 subsequently records deployed portal
OIDC, official console/native data use and active-session revocation for RustFS,
Qdrant, OpenSearch and Neo4j with disposable humans. This qualifies the earlier
browser deferrals below; it does not establish natural timers, operator upgrade
review, off-host restore or domain comparison. EV-71/72 last record seven confirmed
resource purges still awaiting verified scheduled backup, with access revoked.
See the [verification register](../backlog.md#verification-register); this source
documentation review did not recheck the live installation or close the phase.

The owner requested continued implementation as far as possible with regular
commits. Source/local provider work continues alongside remaining deployed and
provider acceptance; passing the PostgreSQL gate does not enable another service.
Native RustFS, OpenSearch, Qdrant and dedicated Neo4j Community adapters now pass
real isolation, credential, query and empty-volume recovery fixtures. Opt-in pinned Compose services,
configuration/capacity-gated provider registration and non-demo OpenSearch TLS
initialization are implemented. The actual production Compose definitions pass
disposable health/administration checks. RustFS, Qdrant and OpenSearch Dashboards
native browser login, RO/RW isolation and active-session expiry/revocation now
pass local TLS fixtures. OpenSearch resource workspaces survive human renewal
and are included in usage, backup/recovery and isolated purge. Deterministic
deployed provider evidence is recorded in EV-68; PostgreSQL is the default
selection. Neo4j uses the
recorded full-instance-access exception, initially one retained resource per project.
See the [RustFS](../../../../persistence/compatibility/rustfs-2026-10-17.md),
[OpenSearch](../../../../persistence/compatibility/opensearch-2026-10-17.md),
[Qdrant](../../../../persistence/compatibility/qdrant-2026-10-17.md) and
[Neo4j](../../../../persistence/compatibility/neo4j-2026-10-17.md) records.

## Deployed deterministic checkpoint — October 18, 2026

EV-68 records a disposable three-project, six-persona run on node-01 with
RustFS, OpenSearch, Qdrant, Neo4j and a PostgreSQL application binding. It
covered provisioning; role and project isolation; same-project and owner-approved
cross-project bindings; rejection, no in-place read-only escalation and native
read-only write denial; component-only managed Secrets with `envPrefix`; native
application writes and reads; hard S3 quota and operator quota admission; native
metrics; native revocation; retirement; and verified-backup-gated isolated purge.
The verified snapshot was `4ff4ea9903b96f9c708e1e0825fa07666657105611a41b97e378dd0461a5e038`.
All five resource states reached `purged/purged`, and their live database,
bucket, collection, index and Neo4j instance were absent. The disposable projects
were retired and their application catalogs purged; named-store history keeps
their reserved project names. All six personas and the runner were revoked.

EV-69 records a separate deployed plain-versus-AGE/pgvector resource check:
scoped writer and reader credentials verified extension selection, an HNSW vector
index, a protected graph projection, nearest-neighbor and transitive graph reads,
and denial of reader writes and unselected extension installation. Both resources
were retired, held at the purge gate until verified backup
`a6cc0515a10cbedaeb00caa06e7616f963470b05fa919d6021b46fea620396b7`,
then reached `purged/purged` with their native databases absent. Their project
catalog, two personas and runner were cleaned up.

The RustFS console Date-header repair and API resource-detail quota-mode repair
were deployed and verified by the relevant fixture and live API checks. The
owner subsequently confirmed deployed interactive RustFS upload, download and
delete; the disposable real-browser fixture now exercises upload and deletion
through the official console. The
local empty-volume recovery fixtures and synthetic analytics comparisons do not
establish deployed off-host restore or domain-quality results. The previously
deferred PostgreSQL time handling and restore checks remain in Phase 10 packages
10.11/10.12; the ODIP-to-VEF check remains omitted from 7.1.

## Implementation checkpoint — October 17, 2026

Source work has started in `app.stores`: independent resource/grant/credential
catalog, versioned administration requests, API authorization boundaries,
PostgreSQL role/database provisioning and lifecycle/workload reconciliation.
The routes and workers are now wired into the source application. The portal
and CLI manage named resources, grants/bindings and human credential leases;
the private relay enforces credential identity and session deadlines. Browser
consoles and the four opt-in providers have local evidence; deployed acceptance
and external domain comparisons remain in progress. See the
[operator workflow](../../../operators/data-stores.md). Eight API
boundary tests and a disposable real PostgreSQL fixture pass resource isolation,
cross-writer schema ownership, future-object read access, read-only denials,
expiry, session revocation, 30-day worker rotation/retry/deadline handling, real
relay authentication/session expiry and isolated purge. The pinned AGE/pgvector runtime image also passes writer/reader graph/vector
queries and denial of graph writes/extension removal. A disposable real
Keycloak → pgAdmin fixture passes SSO, scoped connection/query, password-saving
denial, expired reconnect and anonymous denial. Production console network/TLS
and deployed access acceptance remain open. The backend suite ran
567 tests successfully (16 skipped); the portal suite passes 48 tests. Production
image construction passes, including bundled RustFS assets and exclusion of the
optional DuckDB dependency from the API runtime. The relay and portal tests cover expiry, denial,
explicit issuance and secret-cache exclusion. No live resources were changed.
Source now includes bounded usage measurements/alerts, the named-store dashboard,
restore quarantine, and version-pinned purge acknowledgment after verified
backup upload/readback. A real encrypted local restic intent fixture passes
purge gating and latest-tombstone replay after an older-state simulation; recovery
requires fresh explicit approval. The fixture additionally restores the real encrypted
SQL/catalog backup into an empty second disposable server, replays purge intent,
rebuilds graphs, retains SQL/vector/outbox data and verifies old-key denial/fresh
read-only approval. This is local evidence, not deployed off-host RPO/RTO acceptance.
The [upgrade runbook](../../../operators/runbooks/store-upgrades.md) covers pinned
release checks, verified pre-upgrade backups, extension upgrades and recovery limits.
AGE authoritative rebuild is implemented and passes a real logical-restore
fixture with two graphs, five labels, a cycle, source-defined indexes and preserved
SQL/pgvector data. See the [dated evidence](../../../../persistence/compatibility/projection-rebuild-2026-10-17.md).
Deployed rebuild/reconnection and recovery timing remain open in Phase 10
package 10.13.
Retirement previews include named resource/grant versions; access fencing commits before namespace deletion. The PostgreSQL reference covers JSONB, full-text search, recursive CTEs, partitions, materialized views and transactional outbox rollback in the real database fixture.
PLAN-026/036 and Phase 7 acceptance remain open.

## Goal and scope

Provide the planned analytical, object-storage, search, graph and vector
capabilities through optional generic resource providers and functional integration.
DuckDB/Parquet and one S3-compatible store form the analytical foundation;
OpenSearch, Apache AGE/Neo4j and pgvector/Qdrant follow as targeted experiments.
Stores may be selected at will under the [selection decision](data-store-expansion.md#store-selection-decision).
Measurements and comparisons are separate [Phase 9](phase-9-store-measurement-and-comparison.md)
learning work and do not impose adoption success criteria.

**Entry:** existing PostgreSQL platform capabilities and agreed cross-project
integration contract. Complete package 7.1 before introducing additional stores;
then follow analytics/object storage → search → graph → vector package order,
subject to each package's fixtures. Phase 5 AI operations does not depend on
vector retrieval. Optional Phase 6 and unrelated Phase 10 leftovers do not gate
this work.

**Service placement:** Shared stores run persistently in Docker Compose outside
Kubernetes, alongside PostgreSQL, using the existing operator Compose/Ansible
workflow. Applications remain Kubernetes workloads and access private endpoints
through explicit bindings, managed secrets and network policies. This does not
activate the optional Docker compute adapter. See the
[placement decision](data-store-expansion.md#shared-service-placement-decision).

**Ownership and evidence:** [common acceptance and responsibilities](data-store-expansion.md#ownership-and-common-acceptance)
apply to every package. Track PLAN-026–030 and PLAN-036 in the
[backlog](../backlog.md#data-store-expansion-tasks); Phase 9 tracks cross-store
measurement and comparison separately.

## Measurement and comparison scope

Performance dashboards, quantitative measurements and cross-store/domain
comparisons are in [Phase 9](phase-9-store-measurement-and-comparison.md).
Existing metric pipelines and synthetic comparison fixtures remain available;
their implementation evidence does not make measurements a Phase 7 exit gate.
Phase 7 retains provider health, quota/capacity admission, backup capture and
verified-backup-gated purge. Deployed restore, rebuild and reconnection checks
belong to Phase 10 package 10.13.

## Ordered work packages

### 7.1 — PostgreSQL Baseline and Integration

**Tasks:** PLAN-026 and PLAN-036 (human access paths). **Source:** phase 0. **Entry:** existing PostgreSQL platform
capabilities and agreed external integration contract.

- Enforce the [resource administration policy](data-store-expansion.md#resource-administration-decision):
  project admins manage their own resources, grants and bindings; platform admins
  have those capabilities across all projects. Preserve cross-project approval,
  purge prerequisites/confirmation and audit trails. Native/console data access
  still requires explicit human grants; verify role boundaries and no implicit
  data access from administrative status.
- Implement the [independent project-resource and binding contract](data-store-expansion.md#resource-lifecycle-and-binding-decision)
  for PostgreSQL first: separate named-resource lifecycle, multiple resources per
  project, explicit application/component bindings, scoped credentials/permissions,
  rotation/revocation and independent retention. Verify unbound/foreign component
  denial, binding removal and explicit permanent deletion behavior.
- Apply the [quota exhaustion policy](data-store-expansion.md#storage-quota-exhaustion-decision):
  block storage growth at quota where supported, preserve reads/authorized cleanup
  and alert administrators. Require explicit capacity-checked approval for quota
  increases; verify unaffected-resource isolation and document provider limits,
  including admission/monitoring substitutes where hard quotas are unavailable.
- Implement [owner-approved cross-project resource bindings](data-store-expansion.md#cross-project-resource-sharing-decision):
  consumer-project administrators request access for a named application/component,
  resource-owning project administrators approve its explicit mode, and the platform
  provisions scoped access. Add API/CLI/portal approval/rejection/revocation and
  verify pending denial, scope changes, active-session cleanup and ownership retention.
- Implement the [retention-first lifecycle](data-store-expansion.md#deletion-and-retirement-decision):
  application/binding removal revokes only its consumer access; resource/project
  retirement revokes all affected access and retains data; separate confirmed
  purge requires retirement and completed cleanup. Verify retries, partial cleanup,
  stale confirmation, unaffected consumers and backup-retention/purge semantics.
- Implement [automatic application credential rotation](data-store-expansion.md#application-credential-rotation-decision)
  every 30 days, with managed-secret updates and controlled restarts of bound
  components.
  Applications must tolerate restart; verify readiness and new-credential access
  before promptly retiring the old generation, with at most one hour of overlap. Cover interrupted rotation,
  partial rollouts and revocation across generations without affecting unrelated
  bindings or restarting shared stores. Verify rotation scheduling across controller
  restarts; revoke old credentials and close their connections by the one-hour
  deadline even on failed rollout, reporting recovery needs without extending
  overlap on retries.
- Extend [human access to named resources](data-store-expansion.md#human-access-to-named-resources)
  with explicit read-only/read-write modes, separate resource-scoped human
  credentials and private connection paths. Add API/CLI/portal grant management,
  permission changes, rotation/expiry and revocation. Human credentials must
  [expire and renew against the current active grant](data-store-expansion.md#human-credential-expiry-decision);
  use a 24-hour default credential validity and close active connections at
  credential expiry through private and console access. Require renewal and
  reconnection; renewal must not extend old sessions. Early renewal preserves
  the old credential and its connections until their original expiry while
  issuing a new credential with its own validity. Revocation, retirement and
  permission changes apply across all outstanding credential generations.
  Verify PostgreSQL data-write
  and application-schema DDL permissions for human/application writers, without
  server/global escalation; cover two resources with different grants,
  future objects, cross-resource/project denial and active-session downgrade.
  Permit startup migrations through read-write bindings; a dedicated migration
  identity/job is optional. Verify cross-writer object ownership and removal of
  schema authority on downgrade/revocation. Apply this grant model to each
  subsequently introduced provider.
- Deliver [both private and browser-console access](data-store-expansion.md#private-and-browser-console-access-decision)
  (`PLAN-036`): resource-aware SSH/native-client access and a portal-launched
  authenticated pgAdmin console using each human's scoped resource identity.
  Extend both paths with each selected provider, including its console adapter.
  Verify backend enforcement and revocation/downgrade of existing sessions; raw
  store ports remain private and consoles never receive shared admin credentials.
- Establish [operator-triggered shared-store upgrades](data-store-expansion.md#shared-store-upgrade-decision)
  with pinned images/extensions/consoles, a verified recoverable backup,
  release-specific compatibility checks and an available recovery procedure.
  Applications must tolerate maintenance interruption and reconnect/restart.
  Verify data, scoped access and platform integrations afterward; do not assume
  an older image can read migrated data. Deployed recovery validation is Phase 10
  package 10.13. Keep automatic credential rotation
  independent while preserving its overlap deadline during maintenance.
- Use the owner-accepted clean setup: update and recreate application/resource
  declarations against the new contract. Legacy implicit database provisioning,
  automatic access for every component and compatibility/migration paths are not
  requirements. Record reset steps and impacts before performing recreation.
- Exercise PostgreSQL provisioning; document JSONB, full-text search,
  recursive CTEs, materialized views, partitioning, and transactional-outbox baselines.
- Reuse existing Phase 10 evidence and record newly performed integration
  checks against their original tasks; do not close unrelated leftovers.

**Exit:** the independent resource/binding contract passes PostgreSQL lifecycle,
isolation, named-resource human read-only/read-write access through both private
and browser-console paths; a versioned cross-project resource-binding acceptance record
and reproducible PostgreSQL reference establish the gate for additional stores. Local-only
integration or the imported roadmap's starting-point claims do not satisfy it.

**Deterministic exit accepted (October 18, 2026):** EV-52–67 cover deployed
provisioning, independent lifecycle and verified-backup-gated purge, native and
browser read-only/read-write access, active pgAdmin Query Tool termination on
grant revocation/downgrade and resource retirement, application binding and
rotation, versioned cross-project approval/rejection and ownership, quota
admission, monitoring failure/recovery, plus the reproducible PostgreSQL
reference and focused API/CLI/portal fixtures. Phase 10 packages 10.11/10.12 retain
their explicit restore, elapsed-time and operator-reviewed work. This accepts
the 7.1 entry gate for 7.2, not Phase 7 as a whole.

**Owner scope change (October 18, 2026):** Deployed off-host PostgreSQL restore
acceptance is a [Phase 10 leftover](phase-10-anytime-leftovers.md#1011-verify-deployed-named-postgresql-restore-plan-026-follow-up),
not a package 7.1 exit gate. The local encrypted restore fixture remains evidence,
not a deployed restore result. The ODIP → VEF integration check is omitted from
package 7.1; externally owned energy-system acceptance remains tracked by its
own integration plan and Phase 10 generic integration work.

**Further owner scope change (October 18, 2026):** Run deterministic automated
PostgreSQL acceptance now. Real 24-hour/30-day/one-hour elapsed-time observations,
operator-reviewed live upgrade and human presentation/security reviews are
[Phase 10 package 10.12](phase-10-anytime-leftovers.md#1012-complete-time-dependent-and-operator-reviewed-postgresql-acceptance-plan-026plan-036-follow-up),
not package 7.1 exit gates. Existing controlled-clock fixture results remain
evidence only for their simulated conditions. Any newly discovered deterministic
gap remains Phase 7 work. The deployed pgAdmin Query Tool write,
lifecycle and verified-backup-gated purge, quota/admission requests,
cross-project scope-change/rejection, and exporter outage/recovery checks have
dated evidence in EV-65/66; PostgreSQL byte quota enforcement remains advisory.

**Extension compatibility evidence (October 17, 2026):** PostgreSQL 18.6 with
pgvector 0.8.7, AGE 1.8.0 and deferred TimescaleDB 2.30.2 passed the 16-case local
coexistence/query matrix and restart checks. See the
[version pins, results and limitations](data-store-expansion.md#postgresql-extension-compatibility-check).
AGE-only and combined logical restores reproduced stale graph OIDs; the tested
fixture-only repair is not full recovery acceptance. Implement explicit per-resource
extension selection, safe AGE session/preload configuration and verified AGE
recovery/rebuild as the PLAN-029 follow-up in Phase 10 package 10.13. Live
services remain unchanged.

### 7.2 — Analytics and S3-Compatible Object Storage

**Task:** PLAN-027. **Source:** phase 1. **Entry:** package 7.1 integration acceptance.

**Source/local increment (October 17):** The
[application artifact example](../../../../examples/analytics-artifacts/README.md)
publishes exact-version, checksum-verified Parquet snapshots in a bound RustFS
bucket and verifies them before DuckDB reads local data. Its manifest/reference
contract survives later writes at the same keys and empty-volume restore with
fresh scoped approval. Opt-in fixtures compare scoped PostgreSQL tables, DuckDB
tables and local/versioned-S3 Parquet against a deterministic Python oracle for
daily/monthly aggregation, weather joins, windows and scenario costs. Engine
timings and transfer/checksum cost are separate observations without adoption
thresholds. DuckDB is confined to applications and the optional fixture group.
The 180-row synthetic fixture is not ODIP domain/large-volume acceptance. A
deployed bound-component fixture now verifies atomic PostgreSQL metadata/outbox
publication with an exact-version RustFS artifact (EV-71). Deployed RustFS
browser upload/delete, scoped reader denial and active-session revocation pass
with disposable human personas (EV-72); domain application integration remains
externally owned. Deployed recovery is Phase 10 work.

- Implement owner-selected [RustFS](data-store-expansion.md#object-storage-selection-priority)
  as a shared, continuously running Docker Compose service with its official
  browser console and private native S3 access. Pin verified compatible releases;
  verify scoped console login, 24-hour human credential/session expiry and
  automatic application rotation every 30 days with at most one-hour overlap.
  Preserve the priority of straightforward single-host operation: reproducible
  setup, required S3 behavior, isolation/bindings, bounded resource use, upgrades
  and encrypted off-host backup capture. Future distributed deployment is not
  an initial requirement. Add a generic S3-compatible resource provider backed by
  RustFS with named project buckets, explicit component bindings, scoped
  credentials/policies, limits and lifecycle coverage under the common
  acceptance. Product selection is resolved; deployment and acceptance are open.
  DuckDB is an application analytical engine, not necessarily a shared service.

**Exit:** An application publishes and consumes versioned datasets independently
of physical storage, and the selected object-store provider passes provisioning,
scoped access, backup capture and lifecycle acceptance. Restore acceptance is
Phase 10 package 10.13; comparative analytics are Phase 9 work.

### 7.3 — Full-Text Search

**Source/local checkpoint (October 17, 2026):** The exact-index OpenSearch
provider and official pinned Dashboards are implemented. Real-browser fixtures
pass native login, Discover, read-only/read-write data and mapping permissions,
foreign-resource denial, workspace isolation and renewal, and already-open
session expiry/revocation. Resource-scoped saved views are editable in both
modes; read-only document/schema access remains enforced natively. Native
fixtures pass empty-volume restoration with fresh scoped approval and isolated
workspace/data purge. A deployed synthetic bound-component fixture verifies
PostgreSQL-authoritative create, update and delete projection behavior (EV-71);
domain application integration remains externally owned.
Deployed Dashboards writer/reader login, scoped data operations and active-session
revocation pass in EV-72. Deployed rebuild and recovery acceptance are Phase 10 package 10.13; judged
domain comparisons are Phase 9 work.
See the [compatibility evidence](../../../../persistence/compatibility/opensearch-2026-10-17.md).

**Task:** PLAN-028. **Source:** phase 2. **Entry:** package 7.2 analytical foundation.

- When selected, expose an optional OpenSearch provider; verify
  source-of-truth/update semantics while PostgreSQL remains authoritative.

**Exit:** any introduced provider meets common lifecycle, isolation and
source-of-truth/update acceptance. Index rebuild and restore acceptance are
Phase 10 package 10.13; search quality and latency comparison are Phase 9 work.

### 7.4 — Graph Data

**Task:** PLAN-029. **Source:** phase 3. **Entry:** package 7.3 foundation and
versioned VEF dependency fixtures; Bot Social experiments additionally require Core.

**Implementation constraint verified October 17, 2026:** The current Neo4j
[edition comparison](https://neo4j.com/docs/cypher-manual/25/introduction/cypher-neo4j/)
limits Community Edition to one user database and gives every user full access.
It therefore cannot satisfy the original shared-instance isolation and independent
read-only/read-write grant contract.

**Owner-selected integration decision (October 17, 2026):** Use a dedicated
Community Docker instance and persistent volume per named Neo4j resource,
initially one resource per project, shared through explicit component bindings.
Keep provisioned instances running until retirement. Advertise full instance
access only and reject unsupported read-only grants; this is an explicit
Neo4j-specific placement/access exception. Implement private native access and
Neo4j Browser, separate human/application identities, existing expiry/rotation
and active-session fencing, per-instance capacity/monitoring, offline backup
capture and verified-backup-gated purge. Verify native full-access capabilities
cannot bypass platform identity or lease controls. No Docker socket in the API
or commercial edition is selected. The provider is now opt-in in source with native/Browser/isolation, real catalog,
instance-replacement networking, JVM, expiry and cold-volume recovery fixtures.
Source explicitly reports full-instance access. Deployed Neo4j Browser login,
native graph writes, active-session revocation and independent access for a
second full-access persona pass in EV-72. See the
[local evidence](../../../../persistence/compatibility/neo4j-2026-10-17.md). See the [complete decision](data-store-expansion.md#neo4j-community-dedicated-instance-decision).

- Protect authoritative sources, graph definitions and loaders under the
  [rebuildable-projection policy](data-store-expansion.md#apache-age-rebuild-policy).
  AGE must not hold the sole copy of unique domain data. Preserve non-superuser
  application roles with explicit AGE session/preload configuration. The
  source-backed rebuild and reconnection check is Phase 10 package 10.13.
- Check extension/version compatibility needed for operation. Provide optional
  AGE or Neo4j support when selected, with common operational acceptance.

**Exit:** introduced providers have scoped graph behavior, retained data and
backup capture. Rebuild/recovery evidence is Phase 10 package 10.13;
cross-engine semantic and operational comparison is Phase 9 work;
VEF retains constraint evaluation and optimization responsibility.

### 7.5 — Vector Retrieval and AI Memory

**Task:** PLAN-030. **Source:** phase 4. **Entry:** selected vector resource and
the available platform foundation. Phase 5 operations assistance does not
require this package.

- Add optional extension/provider support when selected. Verify scoped collection
  access, deletion and common lifecycle behavior. Rebuild/restore verification is
  Phase 10 package 10.13.

**Exit:** any adopted provider has scoped collection access, deletion and common
lifecycle evidence. Rebuild/recovery is Phase 10 package 10.13; retrieval-quality
and performance comparison are Phase 9 work.

Deployed Qdrant official-console writer/reader login, collection-scoped point
operations and active-session revocation pass in EV-72.

## Phase exit

All five packages record their disposition and dated operational evidence. PostgreSQL and
the chosen S3 provider are operationally covered; any adopted search, graph or
vector provider passes common lifecycle, isolation, capacity and backup/purge
acceptance. Deployed restore, rebuild and reconnection checks are
[Phase 10 package 10.13](phase-10-anytime-leftovers.md#1013-verify-deployed-data-store-recovery-plan-027plan-033-follow-up).
Quantitative measurements, domain comparisons and the eight
performance dashboards are [Phase 9](phase-9-store-measurement-and-comparison.md)
exit work. Retaining a baseline is a valid documented provider decision.
Unrelated Phase 10 work remains open. The separate
[Phase 8 deferred stores](phase-8-deferred-data-stores.md) activates only for its
owner-selected schedule.
