# Provisioning Sequence

Status: contract draft. [Software architecture](../software-architecture.md).

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant API as Platform API
    participant State as Platform State
    participant Worker as Reconciler
    participant DB as DatabaseProvider
    participant Sec as SecretProvider
    participant Compute as ComputeProvider
    Dev->>API: Spec and expected revision
    API->>API: Authorize, validate, check capabilities
    API->>State: Atomically store spec revision and job
    API-->>Dev: 202 with operation ID
    Worker->>State: Lease job
    Worker->>DB: Ensure database and role
    DB-->>Worker: Stable resource ID / credential reference
    Worker->>State: Persist step
    Worker->>Sec: Ensure binding
    Worker->>Compute: Ensure workload
    alt Workload ready
        Compute-->>Worker: Health and observed revision
        Worker->>State: RUNNING and conditions
    else Provider failure
        Compute-->>Worker: Error or unknown outcome
        Worker->>State: Error, retry state, and existing resources
        Note over Worker,DB: The provisioned database is retained
    end
    Dev->>API: Read operation
    API->>State: Read authorized status
    API-->>Dev: Progress or redacted failure reason
```

Routing and observability are also resumable steps; they are condensed here for readability. After a timeout, the worker observes provider state before attempting creation again.
