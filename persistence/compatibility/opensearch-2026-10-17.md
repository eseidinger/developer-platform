# OpenSearch provider verification — October 17, 2026

Pinned OpenSearch: `opensearchproject/opensearch:3.9.0` at
`sha256:adfa61f85025d06b4aeb562e7e74fde7e31c437039c93c3862c17e9acebd6c7c`.
OpenSearch and its Dashboards project use Apache-2.0. This record covers native
native provider behavior and local Dashboards integration; deployed acceptance
remains open.

Each resource UUID maps to an exact index name and two native roles. Writers can
change document data and field mappings; readers can query and inspect mappings.
Resource deletion, index settings, alias mutation, security administration and
arbitrary index creation are excluded. Exact owned-index alias/resolve metadata
reads are allowed; foreign-index reads remain denied. Credential generations have distinct native users,
passwords and resource/mode role mappings. Revocation deletes the native user;
the outer HTTP relay enforces lease expiry and cuts off outstanding connections.

The real `scripts/verify-opensearch.py` fixture passed:

- Idempotent provisioning and credential issuance across two resources, writer
  mapping changes and indexing, reader text ranking/filter/facet queries.
- Read-only write/schema denial and foreign-index query denial.
- Denial of index deletion, settings changes, arbitrary index creation,
  role/user administration and cross-resource alias creation.
- Mixed bulk indexing: its own index succeeds and the foreign-index item returns
  403. Ordinary document indexing also uses the bulk transport action in this
  release; both modes grant that specific cluster-level action while native leaf
  permissions still enforce exact index scope. It does not grant the broader
  cluster-wide write/alias action group.
- Native credential revocation, repeated cleanup, real lease relay access and
  rejection after revocation; measured native store bytes and isolated purge.

The disposable server uses loopback HTTP, demo transport certificates, a random
synthetic administrator password, a 256 MiB JVM heap and bounded container/data
storage. Those choices are fixture-only. Production construction requires HTTPS
and an operator-owned CA; certificate verification stays enabled. The API receives
only operator-managed native administration credentials and no Docker socket.
OpenSearch internal users have no native lease deadline in this adapter; every
application, tunnel and console data path must use the lease relay. Raw access
would bypass its immediate session/deadline enforcement.

Store-byte quotas remain advisory at this checkpoint. Native global disk
watermarks are not an isolated per-resource byte quota; an index write block
would also prevent authorized document cleanup. Admission and stale/unknown
measurements must remain visible until provider-specific enforcement is verified.

The provider is opt-in behind operator selection, complete TLS configuration and
an explicit capacity budget. Authenticated Dashboards/session integration passes
locally; deployed recovery acceptance remains open. No live resources
were changed. Native role boundaries follow the
[OpenSearch role guide](https://docs.opensearch.org/latest/security/access-control/users-roles/)
and [permission reference](https://docs.opensearch.org/latest/security/access-control/permissions/).

The fixture additionally captures the stopped service’s real Docker volume and restores it into an empty second volume/server. Retained object versions, vectors/payload indexes, or search documents/mappings and native access metadata survive as applicable. Recovered native credentials are revoked before fresh scoped reader approval; unrelated resources remain intact. The common backup code now contains coordinated lease-pause, stopped-volume capture and required-archive restore adapters. Combined deployed encrypted multi-store recovery and deployed browser/session acceptance remain open.

Production Compose wiring additionally passes a disposable native fixture with
the generated CA/server/admin certificates, verified hostname, no demo users,
an unprivileged initializer and working health checks. Repeated preparation keeps
the CA and a second initialization retains existing scoped users. Issue/probe
checks require the exact expected resource role, rejecting ambient broader role
mappings. These checks do not validate deployed TLS renewal. The separate browser fixture
below covers Dashboards locally.

## Official Dashboards integration

Dashboards 3.9.0 is pinned to
`sha256:4bdb8ded547ce7f4c379a10261f1b4aad58726900c215be570a7d1fe86f2a7d8`.
It runs on a separate internal network with the API bridge, no host port, no raw
store network membership and no operator administrator key. A real positive/negative
TCP control reaches the native listener from the store network and cannot reach
the same listener from an isolated console network. The private bridge requires
the exact source service IP and binds human Basic identities to the launched
credential generation before using its native relay. The authoritative resource
tenant is selected by the bridge; caller tenant/lease headers cannot retarget it.

The restricted `kibanaserver` identity initializes only global system metadata
over verified native TLS. Native negative controls deny reading resource documents
and administering users. The official `/app/login` page requests native settings
before sign-in. Only the exact query-free GET to
`/_plugins/_security/dashboardsinfo`, under an active launched human lease, may use
the restricted server identity to read those settings. The realm requires native
authentication even for that read. Data and authenticated user operations require
the matching human Basic identity; no administrator fallback is used.

Unbound server requests cannot select resource tenants or physical resource
console indexes in their URI or decoded JSON/NDJSON payload, including escaped
names. Server metadata writes are bounded to 1 MiB and compressed request bodies
are rejected. This prevents delayed unbound jobs from recreating purged resource
metadata. The pinned UI performs resource migrations under the leased human.
The console's generic index-discovery request is scoped to the owned index;
explicit foreign-index requests remain native-denied. Searches/documents are
not rewritten. Cookie isolation, cross-lease identity denial, source-IP checks,
stale/non-human denial and held frontend-stream expiry/revocation/catalog-stall
closure pass local tests. The gateway retains the official CSP and appends its
own policy rather than replacing upstream script/worker restrictions.

Each resource gets an exact named tenant `resource` plus its UUID hex. Global and
private tenants are disabled; issuance verifies the native private-tenant flag.
Both human modes may edit that resource's saved views, while read-only document,
bulk-document and mapping mutations are denied natively. Native roles grant the
bulk operation class needed by the UI; each bulk item's index permissions still
apply. The metadata does not belong to an expiring credential generation.

**Compatibility finding:** Dashboards must explicitly enable multitenancy in its
UI plugin as well as native security configuration. Omitting the UI flag produced
saved-object text mappings and empty `_find` results despite successful GET by ID.
With multitenancy enabled, native migrations create the expected keyword mappings
and real Discover displays the fixture documents. Preparation records
`console_tenant_policy: resource-v1`, requires its complete bootstrap configuration
and rejects older cached policy rather than silently reusing it.

Resource usage includes the physical tenant indexes. Identification accepts only
the pinned exact owned-index layouts and numeric byte measurements; an unknown
owned layout blocks purge before deletion and requires operator review. Purge
removes owned console indexes, tenant, data index and roles idempotently while
retaining another resource's workspace. Stopped-volume recovery retains the
workspace; recovered keys are revoked before fresh read-only approval.

The real-browser fixture passes read-write, read-only and renewed read-only
native login, Discover document rendering, own/foreign data boundaries, saved-view
isolation and retention across renewal, already-open expiry/revocation, browser
storage cleanup and reload denial. Native keys remain valid in positive controls
so the session-denial evidence does not depend on native deletion. Afterward,
isolated repeated purge removes one resource while preserving the other.
`console.PROVIDERS` includes OpenSearch and the portal advertises its launcher.
Reproduce with `STORE_DASHBOARDS_FIXTURE=1` and
`scripts/verify-shared-store-compose.py`; CI runs this separately from the
RustFS/Qdrant browser fixture because their lease ports overlap.

The full production API image builds with all console assets and imports. These
are synthetic local tests with disposable services; deployed OIDC/DNS/trusted
HTTPS, certificate renewal/capacity, application reconnection, encrypted off-host
multi-store recovery/RPO/RTO, release upgrades and domain search comparisons
remain open. No live installation was changed or enabled by this work.
