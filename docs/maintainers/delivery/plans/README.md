# Active delivery plans

Status: planned work index.

Only unfinished, owned implementation plans belong here:

- [Energy-system use-case enablement priority](energy-system-integration.md)
- [Generic use-case enablement increment](use-case-enablement-increment.md)
- [Phase 4 tracing and Grafana dashboards](phase-4-tracing-and-dashboards.md)
- [Phase 5 AI operations](phase-5-ai-operations.md) — in progress; portal package 5.6 owner-accepted
- [CLI implementation and complete project administration](cli.md)
- [UI implementation](ui.md)
- [Phase 7 planned data stores](phase-7-planned-data-stores.md) — baseline/integration, analytics/object storage, search, graphs and vectors
- [Phase 8 deferred data stores](phase-8-deferred-data-stores.md) — owner-scheduled time series/OLAP, caching and documents
- [Phase 9 anytime leftovers — lowest priority](phase-9-anytime-leftovers.md)

**PLAN-020** [UI increment 4a](ui.md#4a-deliver-hosted-application-access-plan-020)
is owner-accepted for lab sequencing under the exception recorded in the
[backlog](../backlog.md#additional-phase-tasks). Deployed portal journeys remain
unverified; those checks remain in the anytime leftovers phase.

**PLAN-006 CLI source, October 13, 2026:** The [CLI administration plan](cli.md#project-administration-coverage)
now has source commands for every non-health public API operation, including
same-project worker access, human approvals, service credential lifecycle, and
governance. Profile and human device login support are implemented. Local tests,
contract parity, and wheel packaging pass; deployed and role-matrix acceptance
remain open.

When a plan is complete, promote durable behavior to current documentation and
move the plan to `../history/` with its final evidence links.
