# ADR-011 – Lab Watchdog Monitoring Boundary

Created and accepted: September 27, 2026. Status: **Accepted** by the project owner.

## Context

The platform is a side project with one responder and a 24-hour initial response
target. Phase 1A previously required a separate observer to notify when the
external watchdog's scheduler or hosting failed. The owner rejects additional
external monitoring of the watchdog because the extra services and maintenance
would extend monitoring beyond the intended scope of this lab.

## Decision

Keep the existing external watchdog for platform and backup monitoring. Do not
add or require another external service to monitor the watchdog itself. The
monitoring chain ends at the existing watchdog.

Accept that watchdog hosting, scheduler, or notification-path failure may go
unnoticed and that platform or backup incidents during that failure may produce
no notification. Existing status-page freshness checks and manual runbook
inspection remain useful diagnostics, but do not provide independent alerts.
No new manual inspection schedule is imposed by this decision.

## Alternatives

An independent observer could detect watchdog failure but adds another service,
configuration, and maintenance responsibility. The owner explicitly declines
that tradeoff for this lab. Leaving the previous criterion open would incorrectly
treat an accepted scope limit as unfinished implementation.

## Consequences and acceptance

Remove independent watchdog cron/hosting failure detection from Phase 1A and
OPS-007-T01 acceptance. Record it as an accepted limitation, not a passed drill
or deferred implementation task. OPS-007-T01 remains open for its other criteria.

Platform host/cluster failure detection, public application checks, actual alert
and recovery receipt, delivery-failure exercises for the existing channels, and
separate platform/pipeline/backup identities remain in scope. This decision does
not claim that every notification failure can be reported independently.

This decision narrows the lab acceptance scope described by ADR-005; it does not
accept that ADR's remaining proposed capabilities or change the backup policy.

## Review triggers

Revisit if the platform gains availability commitments, additional users who
rely on it, or important workloads for which silent monitoring failure is no
longer acceptable. Additional watchdog monitoring requires a new owner decision.
