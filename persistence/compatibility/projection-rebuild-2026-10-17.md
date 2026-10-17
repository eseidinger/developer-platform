# AGE source-projection recovery — October 17, 2026

Local disposable evidence for PostgreSQL 18.6, AGE 1.8.0-rc0 and pgvector 0.8.7,
using the reviewed source commits in the runtime [Dockerfile](../Dockerfile).
The earlier [coexistence/raw-restore record](results-2026-10-17.txt) remains
unchanged. This tests the owner-selected rebuild route, not an OID catalog repair.

The named-resource fixture creates two graphs with five labels, five vertices,
four edges and a directed cycle. It writes immutable, checksummed source snapshots
through two distinct resource writer logins. Writer deletion/table-drop of source
history is denied. A second writer replaces the graph and persists updated
properties by appending another complete source version. Source-defined GIN and
unique source-key indexes are included.

A real custom-format `pg_dump` and `pg_restore` into a renamed empty database
reproduce the stale AGE graph-OID failure. The renamed fixture reapplies database
ACLs, which a single-database dump omits; full `pg_dumpall` preserves them.
The operator rebuild then uses AGE's normal `drop_graph`/`create_graph` and label
APIs plus the protected sources. It does not update AGE's OID catalogs manually.

After rebuild, graph queries return the expected node/edge counts and updated
properties, including quote/dollar-delimiter test strings. Both declared indexes
exist. Resource read-only queries work; ordinary SQL data and pgvector nearest-
neighbor queries remain intact. Replacement refuses an external application SQL
view and rolls back its pending source insertion instead of cascading into that
view. Recovery revokes old credentials/grants; a fresh approved reader can access
retained data, while the old credential remains denied.

A JSONB-cast source-key index initially failed during restore with `permission
denied for schema ag_catalog` while AGE's SQL `agtype_to_jsonb` wrapper was being
inlined. A native `ag_catalog.->>` expression avoids that wrapper and passes the
same restore/rebuild fixture. This is release-specific evidence, not a general
claim about arbitrary AGE expression indexes or SQL dependencies.

The encrypted local-restic fixture captures a real PostgreSQL SQL dump and current
resource intents while holding the shared lifecycle lock. It verifies exclusion
of concurrent lifecycle mutation, lock release after interrupted capture, refusal
of a retained graph without protected sources, encrypted readback before purge,
and replay of current purge intent after an older-state simulation. It uses a
local repository and sends no notifications.

Run from the root after building the runtime image:

```bash
docker build -t developer-platform-postgres:18.6-vector0.8.7-age1.8.0 persistence
NAMED_POSTGRES_IMAGE=developer-platform-postgres:18.6-vector0.8.7-age1.8.0 \
NAMED_POSTGRES_EXTENSIONS=1 RESTIC_TEST_BINARY=/path/to/restic \
uv run --project platform/app python scripts/verify-named-postgres.py
```

`NAMED_POSTGRES_CONSOLE=1` additionally exercises disposable real Keycloak/pgAdmin
SSO and a scoped connection/query through the expiry relay. The
[named-store CI job](../../.github/workflows/named-stores.yaml) repeats these checks.

This is a same-server disposable database clone plus local encrypted backup test.
It does not establish deployed application/Kubernetes reconnection, off-host
recovery throughput, the four-hour RTO, the 24-hour RPO, physical recovery, arbitrary
graph dependencies, or full AGE regression coverage. Those acceptance items stay open.
