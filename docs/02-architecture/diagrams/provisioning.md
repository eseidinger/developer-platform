# Provisioning Sequence

Status: current request flow followed by the future asynchronous contract. [Software architecture](../software-architecture.md).

## Current synchronous PUT

```mermaid
sequenceDiagram
    actor Admin as Administrator
    participant API as FastAPI
    participant PG as PostgreSQL
    participant Files as Discovery volume
    participant K8s as Kubernetes API
    Admin->>API: PUT project spec + admin bearer token
    API->>API: Validate supported fields
    API->>PG: Acquire global session advisory lock
    API->>PG: Store latest spec / provisioning (autocommit)
    API->>Files: Publish all non-retired catalog targets
    API->>PG: Ensure project login and database
    API->>K8s: Server-side apply fixed resources
    alt All steps completed
        API->>PG: Store applied
        API->>PG: Release lock
        API-->>Admin: 200 applied, namespace and host
        Note over Admin,K8s: Rollout readiness is checked separately
    else Provisioning error
        API->>PG: Attempt to store failed and release lock
        API-->>Admin: 503; repeat the same PUT
        Note over PG,K8s: Existing resources/data remain; no automatic rollback
    end
```

Process termination can leave `provisioning`. Early dependency failures may prevent a catalog update. The monitoring-only thread periodically republishes discovery; it does not resume provisioning. Retirement separately acknowledges an already absent namespace and retains SQL/catalog data. See [ADR-012](../../03-decisions/ADR-012-admin-provisioning-baseline.md) and [ADR-014](../../03-decisions/ADR-014-catalog-availability-monitoring.md).

## Target asynchronous contract

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant Catalog as Application Catalog (Kotlin/Spring)
    participant API as Control Plane (Quarkus)
    participant State as Control-plane State
    participant Worker as Automation Worker (Python)
    participant DB as DatabaseProvider
    participant Sec as SecretProvider
    participant Compute as ComputeProvider
    Dev->>Catalog: Create/update application metadata or grants
    Catalog-->>Dev: Stable application/environment IDs + catalog version
    Dev->>API: Spec, catalog IDs, and expected revision
    API->>Catalog: Resolve identity and current permission facts
    Catalog-->>API: Versioned metadata and authorization facts
    API->>API: Enforce authorization, policy, and capabilities
    API->>State: Atomically store spec revision and job
    API-->>Dev: 202 with operation ID
    API->>Worker: Dispatch immutable job envelope
    Worker->>DB: Ensure database and role
    DB-->>Worker: Stable resource ID / credential reference
    Worker-->>API: Persist structured step result
    Worker->>Sec: Ensure binding
    Worker->>Compute: Ensure workload
    alt Workload ready
        Compute-->>Worker: Health and observed revision
        Worker-->>API: Completed result and observations
        API->>State: RUNNING, conditions, and provider IDs
        API-->>Catalog: Deployment summary event
    else Provider failure
        Compute-->>Worker: Error or unknown outcome
        Worker-->>API: Redacted error, retry state, existing resources
        API->>State: Persist failure and retry decision
        Note over Worker,DB: The provisioned database is retained
    end
    Dev->>API: Read operation
    API->>State: Read authorized status
    API-->>Dev: Progress or redacted failure reason
```

Routing and observability are also resumable steps; they are condensed here for readability. After a timeout, the worker observes provider state before attempting creation again. The worker cannot change the desired revision or expand the plan. Destructive work triggers control-plane reauthorization against the catalog before dispatch or commit.
