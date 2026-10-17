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

The provider stays unregistered until Compose/TLS, coordinated backup/recovery
and authenticated Dashboards/session integration are ready. No live resources
were changed. Native role boundaries follow the
[OpenSearch role guide](https://docs.opensearch.org/latest/security/access-control/users-roles/)
and [permission reference](https://docs.opensearch.org/latest/security/access-control/permissions/).
