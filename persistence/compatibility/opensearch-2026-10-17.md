# OpenSearch provider verification — October 17, 2026

Pinned OpenSearch: `opensearchproject/opensearch:3.9.0` at
`sha256:adfa61f85025d06b4aeb562e7e74fde7e31c437039c93c3862c17e9acebd6c7c`.
OpenSearch and its Dashboards project use Apache-2.0. This record covers native
provider behavior, not deployed acceptance or Dashboards session integration.

Each resource UUID maps to an exact index name and two native roles. Writers can
change document data and field mappings; readers can query and inspect mappings.
Resource deletion, index settings, aliases, security administration and arbitrary
index creation are excluded. Credential generations have distinct native users,
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
  release; the role grants that specific cluster-level action while native leaf
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
an explicit capacity budget. Authenticated Dashboards/session integration and
deployed recovery acceptance remain open. No live resources
were changed. Native role boundaries follow the
[OpenSearch role guide](https://docs.opensearch.org/latest/security/access-control/users-roles/)
and [permission reference](https://docs.opensearch.org/latest/security/access-control/permissions/).

The fixture additionally captures the stopped service’s real Docker volume and restores it into an empty second volume/server. Retained object versions, vectors/payload indexes, or search documents/mappings and native access metadata survive as applicable. Recovered native credentials are revoked before fresh scoped reader approval; unrelated resources remain intact. The common backup code now contains coordinated lease-pause, stopped-volume capture and required-archive restore adapters. Combined deployed encrypted multi-store recovery and browser/session acceptance remain open.

Production Compose wiring additionally passes a disposable native fixture with
the generated CA/server/admin certificates, verified hostname, no demo users,
an unprivileged initializer and working health checks. Repeated preparation keeps
the CA and a second initialization retains existing scoped users. Issue/probe
checks require the exact expected resource role, rejecting ambient broader role
mappings. These checks do not validate deployed TLS renewal or Dashboards.

The candidate Dashboards 3.9.0 image is pinned to
`sha256:4bdb8ded547ce7f4c379a10261f1b4aad58726900c215be570a7d1fe86f2a7d8`.
It runs on a separate internal network with the API bridge, no host port, no raw
store network membership and no operator administrator key. A real positive/negative
TCP control reaches the native listener from the store network and cannot reach
the same listener from an isolated console network. The private bridge requires
the exact source service IP and binds human Basic identities to the launched
credential generation before using its native relay. Only the restricted
`kibanaserver` identity performs background system-metadata initialization over
verified native TLS. The official login page makes an anonymous native login-settings read; that
exact GET is preserved only under an active launched human lease, separately from
authenticated data operations. Cookie isolation, cross-lease identity denial, source-IP
checks, stale/non-human denial, and held frontend-stream expiry/revocation pass
local tests. No native human role is widened. The official login page is
`/app/login`; `/auth/login` is its submission endpoint.

Human browser acceptance remains open. The source-identified anonymous native
configuration read is now represented by a narrow bridge exception; it does not
inject a native credential or alter data permissions. The resource
grant/session/tenant lifecycle and usable data browsing must pass
before advertising browser launch. `console.PROVIDERS` therefore continues to
exclude OpenSearch. The source service/configuration are candidates, not deployed
console acceptance. Use `STORE_DASHBOARDS_FIXTURE=1 STORE_CONSOLE_VERIFY_PENDING=1`
with the existing Compose fixture to reproduce without touching live services.
