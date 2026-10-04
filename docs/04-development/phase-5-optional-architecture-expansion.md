# Optional Phase 5 – Architecture Expansion

Status: optional and unscheduled. It does not gate Phases 2 through 4.

## Entry decision

Keep the existing Kubernetes/k3d workload provider and single Python/FastAPI Platform API unless the project owner records a concrete need that they cannot reasonably satisfy. Activate only the relevant package below; adding a provider does not require splitting the API, and splitting a responsibility does not require adding a provider.

## Optional package A: second compute provider

Add a direct Docker workload adapter only when a real deployment profile requires it. Define a small provider contract around the platform's existing application concepts, then run the same create, deploy, update, observe, recover, and remove acceptance suite on Kubernetes and Docker. Publish capability differences and reject unsupported requests before side effects.

Acceptance requires parity evidence for multi-service applications, scheduled components, machine credentials, authorization, audit, partial failures, retries, and cleanup. The existing Kubernetes path remains available as the rollback path until the new adapter is accepted.

## Optional package B: deployable service extraction

Extract catalog, control-plane, or worker responsibilities only when independently scaling, operating, securing, or evolving one responsibility justifies the added distributed-system cost. The previously proposed technology allocation is Kotlin/Spring Boot for catalog data, Java/Quarkus for control-plane state and policy, and Python for infrastructure execution.

Each extraction requires a versioned contract, separate credentials and state ownership, backfill and reconciliation, authorization and audit correlation, backup/restore coverage, behavior parity, a single-writer cutover, and a bounded rollback path. No service may read another service's tables. Preserve stable project, application, revision, operation, grant, and credential identifiers.

## Acceptance

The activated package resolves its recorded entry need and demonstrates that its operational and migration cost is justified. Contract tests cover success, denial, conflict, interruption, duplicate delivery, partial failure, recovery, and redaction. Existing Phase 2 through 4 workflows continue to pass without client contract changes.

If neither package is activated, the supported architecture remains the single Python API and Kubernetes/k3d provider.
