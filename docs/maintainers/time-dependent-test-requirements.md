# Time-dependent test requirements

Status: draft for discussion, October 18, 2026. This document defines the
boundary between routine deployed API acceptance and checks whose result
depends on a configured period of elapsed time. It does not record a new test
run or change a product retention policy.

## Rule for the deployed API suite

The routine [deployed API acceptance suite](delivery/plans/deployed-api-acceptance.md)
must omit a check when the assertion can pass only after a token, lease, session,
request, schedule, retention period, rotation window, or similar configured
deadline has elapsed. It may inspect the published deadline or retention
configuration as metadata, but that observation is **not** proof that the
deadline is enforced.

Short, bounded polling for a submitted deployment, policy activation,
revocation propagation, or cleanup to reach a terminal state remains part of
ordinary acceptance. In those checks, elapsed time is only a practical wait
for an event already triggered. Do not wait out a product timeout merely to
keep a test in the routine suite.

An immediate denial after explicit revocation stays in the routine suite:
revocation is the event being tested, and the token should still be within its
lifetime. A check that the same token fails **because it naturally expired**
belongs to a timed suite.

## Checks excluded from routine deployed API acceptance

| Capability | Timed behavior to test separately | Routine API suite may still check |
| --- | --- | --- |
| OIDC and automation credentials | Natural access-token, test-runner, test-persona, and deployment-credential expiry; denial after the configured deadline. | Token exchange while active; invalid, missing, or wrong-audience token denial; one-time secret handling; immediate grant or credential revocation. |
| Credential rotation | The predecessor stops working at the end of its configured overlap window; long rotation or adoption deadlines. | Returned overlap metadata; both generations usable immediately after an overlapping rotation; explicit predecessor revocation and immediate denial. |
| Hosted application sessions and access | Browser idle and absolute session limits, maximum authorization-staleness interval, pending-request expiry, and any 24-hour adoption or cleanup timeout. | Login, policy activation, approval, route/group decisions, CSRF, immediate revocation, and explicit credential adoption. |
| Database and store access | SQL/SSH/Bolt/HTTP lease expiry, periodic credential rotation, and expiry of an already established session where a real deadline must pass. | Grant, connection, query, key or password rotation, foreign-resource denial, and explicit revocation/session termination. |
| Scheduled components | A CronJob fires at its scheduled time, repeated cadence, and `Forbid` non-overlap across actual schedule boundaries. | Declaration validation, resource creation and status, invalid schedule rejection, and immediate component changes. |
| Logs, audit, metrics, traces, and artifacts | Seven-day or other configured retention, eventual deletion after retention, and time-window completeness that requires elapsed history. | Immediate ingestion and scoped readback, cursor behavior, redaction, advertised retention settings, and survival across an application restart or rollback. |
| Backup and recovery | Scheduled capture cadence, overdue/stalled thresholds, and age-based retention or pruning. | Configuration validation and explicitly triggered capture/restore checks in their separate operational suite. |

The list is a classification rule, not a claim that every named timer already
has an implemented test. Add newly introduced time-dependent behavior here
when it is added to the API or product contract.

## Where these checks belong

- **CI:** Test deadline calculations and enforcement with controlled clocks,
  short-lived disposable dependencies, and fake scheduler events where useful.
  Such tests prove code behavior under simulated time. Label them as simulated
  time and do not report them as deployed elapsed-time evidence.
- **Timed deployed suites:** Use separate, opt-in runs for real clock passage.
  Each run records a unique ID, the exact target environment and revision,
  the start timestamp, the provider-issued or platform-recorded deadline, the
  earliest valid recheck time, and both pre-deadline and post-deadline results.
  Protect any credentials needed for a later recheck outside Git and ordinary
  logs. Make the check resumable after controller restart and clean up only
  resources owned by that run.
- **Operational schedules:** Backup cadence, telemetry retention, and similar
  multi-day observations may need a scheduled verifier and independent evidence
  retention. They are not part of a one-shot API acceptance command.

Do not change the deployed host, database, or identity-provider clock to make a
real-time check finish early. A simulated-time CI pass and a successful timed
deployed run are different evidence. Record `not run`, `scheduled`, `passed`,
or `failed` separately; never turn an omitted timed check into a passing
routine-suite assertion.

## Existing starting points

The [platform acceptance guide](../operators/validation/acceptance.md#scheduled-expiry-verification)
documents a separate one-day test-runner expiry drill. The
[hosted-access harness](../../scripts/tests/platform/check-hosted-access.py) has
an optional
`--timed` machine-token check and lists longer session, rotation, request,
and retention checks as deferred. The
[component playbook](../../ansible/tests/platform/test-platform-components.yml)
waits for a
real scheduled run. These remain separately reported evidence if invoked;
the new routine API suite must not absorb their elapsed-time assertions.

Related scope: [testing requirements](testing-requirements.md) and the
[deployed API suite plan](delivery/plans/deployed-api-acceptance.md).
