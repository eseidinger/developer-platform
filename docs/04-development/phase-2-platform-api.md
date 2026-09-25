# Phase 2 – Stable Contract and Provider Portability

Status: planned. Covers [F-04, F-07, F-08, N-01, and N-02](../01-product/requirements.md).

## Goal

Evolve the working hybrid path into a reliable control plane and execute the same use case directly on Docker.

## Work packages

1. Compare the actual API with [ApplicationSpec](../02-architecture/application-spec.md); implement the schema, OpenAPI contract, and versioning rules.
2. Model capabilities and service profiles per environment. Remove backend-specific fields from the public contract.
3. Harden persistent jobs, revisions, concurrent updates, retries, drift handling, and deletion plans.
4. Add a Docker adapter alongside Kubernetes; reuse database and observability providers.
5. Build provider contract tests and integration tests for partial failures.
6. Decide [ADR-006](../03-decisions/ADR-006-python-quarkus-evolution.md) after code analysis. If migration is chosen, treat parity and state migration as separate work packages.
7. Complete the fit-gap assessment in the [ADR index](../03-decisions/README.md) before stabilizing the schema.

## Acceptance

Deploy, update, observe, and remove the same portable application in two environments. Unsupported capabilities produce clear errors before side effects. Worker interruption and concurrent updates cause neither duplicate resources nor lost revisions.

Provider failure leaves the job in a traceable state; recovery observes existing resources. Public errors do not expose provider credentials.

## Outcome

A versioned core contract, a published capability matrix for actually tested profiles, and documented differences. Demonstrate portability by execution, not merely by implementing two interfaces.
