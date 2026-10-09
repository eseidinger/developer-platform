# ADR-016 – Phase 1A Recovery-Exercise Scope

Created and accepted: October 1, 2026. Status: **Accepted** by the project owner. Partially supersedes [ADR-010](ADR-010-single-environment-lab.md) for Phase 1A recovery acceptance.

## Context

Phase 1A originally included a restore into an empty isolated installation, failure cases for unavailable or corrupt backups and keys, and a recurring full-recovery exercise schedule. ADR-010 already forbids provisioning an additional lab environment by default, leaving those criteria deferred and preventing the 1A gate from closing despite the selected single-environment operating model.

The project owner has decided to omit those final recovery-exercise steps from the Phase 1A scope. This is a scope change, not evidence that a full restoration has passed.

## Decision

Phase 1A requires backup inventory and recovery access planning, encrypted off-host scheduled capture, verified readback, retention/access controls, and independent failed/overdue/stalled backup signals. It does not require:

- a new empty-host or isolated restoration exercise;
- injected corrupt/unavailable backup or recovery-key exercises; or
- a recurring full-restoration schedule.

Keep the documented replacement-host procedure and independently recoverable credentials. Existing isolated-restoration evidence remains historical reference material, but is not required to close Phase 1A. The deferred recovery-exercise task may be scheduled only through a later explicit scope decision or an actual recovery event.

## Consequences

Phase 1A can be assessed against its remaining protection controls without treating an in-place restart as an isolated restore. It does not establish end-to-end restoration, measured RPO/RTO, recovered application transactions, recovery notification delivery, or behavior with corrupted backups or unavailable keys. These limitations must remain visible in the backlog and operations documentation.

Do not represent the backup design as fully recovery-verified. Revisit this decision before relying on the platform for important user data, materially expanding persisted state, changing backup format or credentials, or making availability/recovery commitments.
