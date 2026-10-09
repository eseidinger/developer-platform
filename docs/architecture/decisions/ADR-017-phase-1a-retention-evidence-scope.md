# ADR-017 – Phase 1A Retention-Evidence Scope

Created and accepted: October 1, 2026. Status: **Accepted** by the project owner.

## Context

The lab backup policy retains 14 daily, 8 weekly, and 6 monthly verified recovery points. Demonstrating that full horizon requires elapsed time far beyond the Phase 1A delivery gate. The scheduled backup, encrypted off-host transfer, exact readback, repository integrity check, scoped retention implementation, access controls, and failed/overdue/stalled backup signals already have the evidence recorded under OPS-006-T02.

The remaining Phase 1A blocker is only elapsed-time evidence that the complete 14/8/6 policy has retained its selected points.

## Decision

Omit long-horizon retention evidence from Phase 1A acceptance. The configured 14/8/6 policy remains the operating policy; Phase 1A requires that it is configured, scoped to verified snapshots, and exercised by a successful scheduled capture/readback/retention run, but not that every daily, weekly, and monthly retention interval has elapsed.

Mark OPS-006-T02 complete using the existing recorded evidence. Do not infer that the full retention horizon has been demonstrated.

## Consequences

This removes the final Phase 1A blocker. It does not establish retention behavior across the complete policy horizon, measured RPO/RTO, or production-grade recovery guarantees. Inspect retention inventory and repository integrity during normal operation, and revisit the evidence before production-like acceptance, a retention-policy change, or any commitment that relies on retained recovery-point history.
