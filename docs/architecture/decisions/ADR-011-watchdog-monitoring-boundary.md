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

## Specific backup-monitoring limitation

On September 28, 2026, the owner accepted that the lab will not exercise a
missing backup update while Prometheus and Alertmanager are unavailable. The
existing external watchdog has already demonstrated no-backup, failed-capture,
stalled, and overdue notifications with recovery. The combined outage exercise
would deliberately suppress local observability and hold backup freshness beyond
its target for an extended period; the owner declines that cost for this lab.

Accept that this lab has no live evidence that the external backup watchdog
continues to notify while local monitoring is down. This is an accepted coverage
limit, not a passed check. It does not disable the external watchdog or alter its
backup freshness rules. Revisit if monitoring availability or backup assurance
becomes a commitment.

## Notification-delivery limitation

On September 28, 2026, the owner also accepted that this lab will not inject or
exercise SMTP or other notification-delivery failures. Successful Alertmanager
and external-watchdog alert/recovery receipt has been demonstrated, but there is
no live evidence of operator-visible behaviour when either channel cannot deliver
email. This avoids deliberately interrupting the only notification path for a
side project with no additional responder or notification service.

Treat undetected or delayed notification-delivery failure as an accepted lab
risk. This does not change SMTP configuration, normal logging, or successful
delivery checks. Revisit before availability commitments, important workloads,
or additional users depend on the platform.

## Backup-corruption injection limitation

On September 28, 2026, the owner accepted that the lab will not deliberately
corrupt, delete, or alter objects in its only live restic repository to simulate
a corrupt backup. That action could damage the sole recovery source and would
require a separate disposable repository or recovery environment, which the
owner does not want to maintain for this lab.

The lab retains live repository `check`, verified-backup readback, and recovery
failure-preflight evidence, plus automated checksum-rejection tests. It has no
live evidence from an intentionally corrupted S3 object or corrupted verified
snapshot. Treat delayed discovery of provider-side or stored-object corruption
as an accepted lab risk. Revisit before the repository protects important
workloads or recovery commitments.

## Alternatives

An independent observer could detect watchdog failure but adds another service,
configuration, and maintenance responsibility. The owner explicitly declines
that tradeoff for this lab. Leaving the previous criterion open would incorrectly
treat an accepted scope limit as unfinished implementation.

## Consequences and acceptance

Remove independent watchdog cron/hosting failure detection from Phase 1A and
OPS-007-T01 acceptance. Record it as an accepted limitation, not a passed drill
or deferred implementation task. OPS-007-T01 remains open for its other criteria.

Platform host/cluster failure detection, public application checks, actual alert and recovery receipt and separate platform/pipeline/backup identities remain in scope. Notification-delivery-failure injection is an accepted limitation described above. This decision does
not claim that every notification failure can be reported independently.

This decision narrows the lab acceptance scope described by ADR-005; it does not
accept that ADR's remaining proposed capabilities or change the backup policy.

## Review triggers

Revisit if the platform gains availability commitments, additional users who
rely on it, or important workloads for which silent monitoring failure is no
longer acceptable. Additional watchdog monitoring requires a new owner decision.
