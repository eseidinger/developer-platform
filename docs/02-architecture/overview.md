# Architecture Overview

Status: consolidated target architecture. The technology-independent API and hybrid starting topology are confirmed; specific interfaces and component boundaries are drafts.

## Three responsibility layers

1. **Infrastructure foundation:** hosts, Docker/Kubernetes, PostgreSQL servers, networking, edge/TLS, monitoring, and backups. Managed through installation and infrastructure as code.
2. **Platform control plane:** projects, environments, ApplicationSpec, authorization, resource lifecycle, provider selection, and status. Provisions resources on existing infrastructure.
3. **Developer experience:** API, CLI, and later a portal and AI assistant. All use the same domain operations.

```mermaid
flowchart TB
    Human["Developer / Operator"] --> Clients["CLI / Portal"]
    Human --> AI["AI Assistant / MCP"]
    Clients --> API["Platform API"]
    AI --> API
    API --> Auth["Authorization"]
    Auth --> Core["Domain and Application Services"]
    Core --> State[("Desired State / Operations / Audit")]
    State --> Worker["Reconciler"]
    Worker --> Compute["ComputeProvider"]
    Worker --> DB["DatabaseProvider"]
    Worker --> Secret["SecretProvider"]
    Worker --> Net["NetworkProvider"]
    Worker --> Obs["ObservabilityProvider"]
    Compute --> Docker["Docker"]
    Compute --> K8s["Kubernetes / k3d"]
    DB --> PG["External PostgreSQL Server"]
    Secret --> Bind["Runtime Bindings"]
    Net --> Route["Proxy / Ingress"]
    Obs --> Telemetry["Prometheus / Loki / Future Traces"]
```

## Domain boundaries

A Project owns Environments. An Application describes a logical application; a Deployment associates a revision with an Environment. Workload, Resource, and Endpoint are addressable targets. A Principal receives allowed actions through Grants.

Providers can be combined independently: Kubernetes compute can use the same external PostgreSQL instance and observability stack as Docker compute. The API does not use namespaces or Compose project names as public identities.

The initial Application consists of an OCI image, HTTP endpoint, configuration, and optional PostgreSQL binding. Multi-component applications are a later extension. Database data is independent of the workload lifecycle.

## Desired state, observed state, and limits

The API stores intent; a reconciler converges resources toward it. An accepted request is not yet a successful deployment. Status includes the observed revision, conditions, and failure reasons.

Portability covers the contract, not automatically identical availability, network isolation, or rollout guarantees. Environments report verified capabilities. Migrating persistent data remains a planned operational process.

Details: [Software architecture](software-architecture.md), [Infrastructure](infrastructure.md), [ApplicationSpec](application-spec.md), [Decisions](../03-decisions/README.md).
