# PostgreSQL reference capabilities

Execute `baseline.sql` once against an empty named resource using its scoped
read-write credential. It exercises JSONB/GIN, full-text search, recursive graph
input, range partitioning, a materialized view and a transactional outbox. No
optional extension or server privilege is needed.

The disposable named-store fixture checks JSONB/FTS lookup, cycle-safe recursive
reachability, partition/materialized-view reads, shared-writer DDL, and atomic
rollback of data/outbox changes. Managed readers can query current/future objects
but cannot mutate them. This is a neutral reference, not an external domain
benchmark or deployment/recovery acceptance record.
