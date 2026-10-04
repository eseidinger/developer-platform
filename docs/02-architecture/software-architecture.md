# Software Architecture

Status: the selected architecture through Phase 4 is one Python/FastAPI Platform API application. It owns platform metadata, grants, desired revisions, operations, policy, runtime observation, and infrastructure execution. Project workloads run only on the existing Kubernetes/k3d infrastructure. A second compute adapter or deployable service extraction is optional Phase 5 work.

## Application boundary

The [Python API](../../platform/app/main.py) is the single public and operational application. Logical responsibilities remain separated in code so they can be tested and evolved without creating distributed services:

| Responsibility | Ownership in the Python application |
|---|---|
| API and identity | OIDC authentication, request validation, versioned HTTP contract, and operation status |
| Catalog and authorization | Projects, application specifications, stable IDs, grants, and machine credentials |
| Lifecycle and policy | Desired revisions, capability checks, concurrency control, rollback, retirement, and audit |
| Operation execution | Durable queued operations, authorization rechecks, retries, and redacted results |
| Infrastructure integration | PostgreSQL provisioning, Kubernetes resources, routing, secrets, and monitoring discovery |
| Runtime observation | Readiness, component status, logs, resource usage, drift, and failure reasons |

These are module and data-ownership boundaries inside one deployable application. They do not imply network APIs, separate service identities, separate deployments, or independently operated databases.

## Request and operation flow

Each state-changing request authenticates the caller, checks the current platform grant, validates the public contract and supported capabilities, then atomically stores the desired revision and durable operation before returning `202 Accepted`. Repeated requests for an unchanged revision reuse its active operation. Expected-revision checks prevent stale updates.

The in-process worker claims queued or interrupted operations using database locks, rechecks authorization and revision freshness, and executes the approved steps. It ensures the PostgreSQL database/login, generates Kubernetes resources, applies them with server-side apply, publishes monitoring discovery, and records a redacted result. The worker observes existing state before retrying operations whose outcome may be unknown.

Catalog, PostgreSQL, and Kubernetes changes are not one transaction. Partial failures therefore remain visible as durable operations. Idempotent `ensure`, observation, retry, rollback, and retirement behavior prevent blind recreation or implicit data deletion.

## Public contract

The API uses platform concepts such as projects, applications, components, revisions, operations, grants, resources, and endpoints. Clients do not submit namespaces, Kubernetes kinds, Compose projects, or provider credentials. Unsupported capabilities are rejected before infrastructure side effects.

Technology independence is a contract constraint, not a requirement to implement multiple providers. The capability endpoint describes the selected Kubernetes environment. Error responses use stable platform categories and redact backend details while retaining an operation ID for authorized diagnosis.

## Infrastructure implementation

The Python application integrates directly with the selected infrastructure:

- Kubernetes/k3d for application services, scheduled components, Secrets, Services, and Ingress;
- PostgreSQL outside k3d for platform state and project databases;
- Caddy and Traefik for edge and cluster routing;
- Prometheus, Loki, Grafana, Alertmanager, and discovery files for observability;
- Keycloak through the generic OIDC boundary for authentication and machine identities.

There is no direct Docker application-workload adapter. Docker remains the host runtime for the platform, identity, persistence, monitoring, and k3d containers.

## State and lifecycle

The application persists stable project/application IDs, immutable desired revisions, operations, grants, credentials, audit records, and retirement inventories in platform-owned PostgreSQL state. Hosted application databases remain logically separate. Persistent data defaults to retention when workload resources are removed; permanent deletion requires an explicit authorized decision.

An accepted operation means the desired state was recorded, not that the workload is healthy. Operation results and live runtime observations remain distinct. Drift is reported rather than silently repaired unless a future policy explicitly enables reconciliation.

See the [current provisioning sequence](diagrams/provisioning.md), [ApplicationSpec](application-spec.md), [security model](security.md), and [Phase 2C capability plan](../04-development/phase-2c-platform-capabilities.md).

## Optional Phase 5

If a concrete need is recorded, [optional Phase 5](../04-development/phase-5-optional-architecture-expansion.md) may add a direct Docker workload adapter or extract one or more deployable services. Neither package is part of the current architecture, and neither gates Phases 2 through 4. Any activated package requires contract parity, state migration, authorization, audit, backup/restore, operational evidence, and rollback before replacing an existing path.
