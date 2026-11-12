# Active delivery plans

Status: planned work index.

This index contains active work and retained completion/exception records. The
Phase 4 plan is a completed record kept at its existing path for evidence links;
current behavior belongs in the canonical guides. A plan's unchecked criteria
must not be read as proof that the corresponding source capability is absent:

[ADR-022](../../../architecture/decisions/ADR-022-postgresql-and-s3-storage-scope.md)
supersedes non-PostgreSQL, non-S3 provider expansion and comparison work in the
Phase 7–9 plans below. Those plans remain for implementation history and
evidence. [PLAN-039](storage-scope-reduction.md) now owns retirement, migration,
source cleanup, and capacity verification.
[PLAN-040](postgresql-extension-expansion.md) follows it with four PostgreSQL
extensions. [PLAN-041](mantine-ui-migration.md) follows PLAN-040 with the
portal's Mantine migration.

- [Deployed Platform API acceptance suite](deployed-api-acceptance.md) —
  proposed first installed-platform test stage
- [Energy-system use-case enablement priority](energy-system-integration.md)
- [Protected identity lookup for hosted applications](identity-lookup.md) —
  planned application-scoped identity API
- [Generic use-case enablement increment](use-case-enablement-increment.md)
- [Phase 4 tracing and Grafana dashboards](phase-4-tracing-and-dashboards.md)
- [Phase 5 AI operations](phase-5-ai-operations.md) — in progress; portal
  package 5.6 owner-accepted
- [CLI implementation and complete project administration](cli.md)
- [UI implementation](ui.md)
- [Mantine UI migration](mantine-ui-migration.md) — PLAN-041; follows PLAN-040
  while preserving portal behavior and API boundaries
- [Storage scope reduction](storage-scope-reduction.md) — PLAN-039; retain
  PostgreSQL and S3, retire other providers, and verify workload capacity
- [PostgreSQL extension expansion](postgresql-extension-expansion.md) — PLAN-040;
  after PLAN-039, add TimescaleDB, PostGIS, pgmq, and pg_duckdb
- [Phase 7 planned data stores](phase-7-planned-data-stores.md) —
  historical baseline/integration and provider expansion scope
- [Phase 8 deferred data stores](phase-8-deferred-data-stores.md) —
  historical deferred provider scope
- [CouchDB provider](couchdb-provider.md) — source, disposable fixture and
  bounded deployed access checks recorded under superseded Phase 8 scope
- [HugeGraph provider](hugegraph-provider.md) — source and disposable fixture
  results recorded under superseded Phase 8 scope
- [Phase 9 data store measurement and comparison](phase-9-store-measurement-and-comparison.md)
  — historical performance dashboard and comparison scope
- [Phase 10 anytime leftovers and store recovery — lowest priority](phase-10-anytime-leftovers.md)

**PLAN-020**
[UI increment 4a](ui.md#4a-deliver-hosted-application-access-plan-020) is
owner-accepted for lab sequencing under the exception recorded in the
[backlog](../backlog.md#additional-phase-tasks). Deployed portal journeys remain
unverified; those checks remain in the anytime leftovers phase.

**PLAN-006 CLI source, October 13, 2026:** The
[CLI administration plan](cli.md#project-administration-coverage) now has source
commands for every non-health public API operation, including same-project
worker access, human approvals, service credential lifecycle, and governance.
Profile and human device login support are implemented. Local tests, contract
parity, and wheel packaging pass; deployed and role-matrix acceptance remain
open.

When a plan is complete, promote durable behavior to current documentation and
move the plan to `../history/` with its final evidence links.
