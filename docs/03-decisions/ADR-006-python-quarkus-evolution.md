# ADR-006 – Python Prototype and Possible Quarkus Evolution

Created: September 25, 2026. Status: **Open**.

## Context

The initial implementation uses Python. Its existing functionality must be inspected before describing the control plane as a Java system or replacing it.

## Options

| Option | Benefit | Cost/risk |
|---|---|---|
| Continue with Python | Existing automation and rapid development | Deliberately enforce typing, domain boundaries, and workflow robustness |
| Quarkus core | Java reference architecture and typed domain | Rewrite, migration, and parity verification |
| Quarkus plus Python worker | Domain core and specialized automation | Additional operational, authentication, and distributed-workflow complexity |

## Interim approach

Inspect the Python prototype first and preserve the existing vertical slice. Do not rewrite solely to demonstrate another technology. Quarkus can be demonstrated independently in a sample application.

Implementation language does not change ApplicationSpec or provider domain boundaries. A mixed-language architecture is justified only if clear responsibilities deliver measurable value.

## Decision criteria

Evaluate code quality, testability, job resumption, team expertise, maintenance effort, and the desired portfolio focus using the existing code. If migrating, verify API parity, metadata/job migration, rollback, and credential ownership.

Next decision point: [Phase 2](../04-development/phase-2-platform-api.md). Neither replacing Python nor adopting Quarkus has been decided.
