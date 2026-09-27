# ADR-010 – Single-Environment Lab Operations

Created and accepted: September 27, 2026. Status: **Accepted** by the project owner.

## Context

The existing platform on node-01 and its external watchdog are a lab. The owner
wants to keep setup and operation simple and explicitly does not want additional
platform test environments. A separate watchdog installation was suggested for
backup failure exercises; the owner rejected the need for that extra environment.

## Decision

Use the existing platform and external watchdog for operational acceptance.
Do not provision or require a separate staging/test platform, recovery VM, or
duplicate watchdog as the default next step. Local automated tests and short-lived
fixtures remain appropriate; they do not imply another deployed platform.

Run controlled, reversible exercises in the existing lab. Temporary service
interruptions and real test notifications are acceptable within a described
exercise. Explain expected impact and duration, preserve the original settings,
provide restoration steps, and verify recovery. Prefer bounded fault injection
with automatic cleanup where practical.

Keep backup contents, keys, credentials and verified-success history intact.
Do not fabricate a successful backup or silently rewrite capture timestamps to
make an acceptance check pass. Destructive replacement of the installation or
deletion of real data is not authorized by this decision.

## Alternatives

- A separate test platform and watchdog would isolate exercises but adds setup,
  resource usage and ongoing maintenance that the owner does not want.
- Local fixtures alone are simpler but cannot establish real notification
  delivery or operational recovery.

## Consequences and acceptance

This decision supersedes generic guidance to use a separate environment for
routine operational failure checks. The external watchdog remains outside the
platform host; its independent placement is part of the operational installation,
not a duplicate test environment.

Previously completed isolated recovery drills remain valid historical evidence.
New empty-host restoration exercises are deferred under the current constraint;
do not create a new recovery environment or treat an in-place service restart as
equivalent proof. Any criterion requiring a fresh isolated restore stays open
until its evidence is supplied or the requirement is explicitly revised. This
decision changes the test approach, not the meaning of successful restoration
or the status of an untested acceptance criterion.

Record each live exercise's target, revision when available, injected condition,
impact, notification receipt and recovery in the delivery backlog. Distinguish
lab evidence from production-grade availability guarantees.

## Review triggers

Revisit before hosting important user data, onboarding users who require
availability, or performing an exercise that cannot be safely reversed in place.
A separate environment would require a new explicit owner decision.
