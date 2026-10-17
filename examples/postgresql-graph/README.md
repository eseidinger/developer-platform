# Rebuildable AGE projection

Create a PostgreSQL resource selecting `age`, then use an explicit read-write
binding or a human read-write lease. Forward the private lease port before using
a remote native client. Supply the scoped `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGPASSWORD` and `PGSSLMODE` through your client environment/secret store.

From the platform checkout with the application environment installed:

```bash
uv run --project platform/app python -m app.stores.projections < examples/postgresql-graph/source.json
```

The loader accepts a complete versioned graph snapshot, appends its immutable
source/hash/revision to operator-owned `platform_control.graph_sources`, and
replaces the derived graph in one transaction. The data writer can append/read
sources and manage graph data; it cannot alter/delete source history or its table.
Each update gets a new revision and a server-assigned ordinal. Explicit labels,
GIN property indexes and unique source-key indexes are recreated from the source.
Custom indexes/constraints need protected definitions/loaders too. This history is included in encrypted SQL backups.

Use stable source keys, available as `__platform_source_key` properties in AGE.
Internal AGE graph/vertex IDs change on rebuild and must not be authoritative
references in other stores. Changes made directly in Cypher are durable only when
also represented in a protected source snapshot. Direct changes absent from the
source will be replaced on recovery. External domain loaders/definitions remain
their projects' responsibility; format 1 is the platform's generic snapshot loader.

A graph deletion is another empty snapshot, with `state: "deleted"`. Keep its source
tombstone instead of deleting history. The initial helper/rebuild limit is 64 graph
identities per resource, eight MiB per serialized snapshot, 10,000 vertices and
50,000 edges. Property nesting, strings, identifiers and numbers are bounded.

Replacement refuses external SQL dependencies on graph schemas/tables. Avoid
persistent SQL views/foreign keys that depend directly on generated AGE objects;
they need separately protected definitions/loaders before replacement is supported.
Resource-managed extension/ACL changes and security-definer routines remain
operator privileges. Ordinary application-schema create/alter/drop stays available.
