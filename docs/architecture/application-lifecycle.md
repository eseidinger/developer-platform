# Application lifecycle

Status: the selected architecture through Phase 5 is one Python/FastAPI Platform
API application. It owns platform metadata, grants, desired revisions,
operations, policy, runtime observation, and infrastructure execution. Project
workloads run only on the existing Kubernetes/k3d infrastructure. A second
compute adapter or deployable service extraction is optional Phase 6 work.

## Application boundary

The [Python API](../../platform/app/src/app/main.py) is the single public and
operational application. Logical responsibilities remain separated in code so
they can be tested and evolved without creating distributed services:

- **Responsibility:** API and identity
  - **Ownership in the Python application:** OIDC authentication, request
    validation, versioned HTTP contract, and operation status
- **Responsibility:** Catalog and authorization
  - **Ownership in the Python application:** Projects, application
    specifications, stable IDs, grants, and machine credentials
- **Responsibility:** Lifecycle and policy
  - **Ownership in the Python application:** Desired revisions, capability
    checks, concurrency control, rollback, retirement, and audit
- **Responsibility:** Operation execution
  - **Ownership in the Python application:** Durable queued operations,
    authorization rechecks, retries, and redacted results
- **Responsibility:** Infrastructure integration
  - **Ownership in the Python application:** PostgreSQL provisioning, Kubernetes
    resources, routing, secrets, and monitoring discovery
- **Responsibility:** Runtime observation
  - **Ownership in the Python application:** Readiness, component status, logs,
    resource usage, drift, and failure reasons

These are module and data-ownership boundaries inside one deployable
application. They do not imply network APIs, separate service identities,
separate deployments, or independently operated databases.

## Request and operation flow

Each deployment request authenticates the caller, checks the current platform
grant, validates the public contract and supported capabilities, then atomically
stores the desired revision and durable operation before returning
`202 Accepted`. Other mutations use their domain's resource/version and response
contract. Repeated requests for an unchanged revision reuse its active
operation. Expected-revision checks prevent stale updates.

The in-process worker claims queued or interrupted operations using database
locks, rechecks authorization and revision freshness, and executes the approved
steps. It resolves approved named-store bindings, generates component-scoped
Secrets and relay-port egress, applies Kubernetes resources with server-side
apply, publishes monitoring discovery, and records a redacted result. A separate
store worker provisions independent resources and reconciles grants and
credential rotation; deployments never create an implicit project database. The
worker observes existing state before retrying operations whose outcome may be
unknown.

Catalog, PostgreSQL, and Kubernetes changes are not one transaction. Partial
failures therefore remain visible as durable operations. Idempotent `ensure`,
observation, retry, rollback, and retirement behavior prevent blind recreation
or implicit data deletion.

## Public contract

The API uses platform concepts such as projects, applications, components,
revisions, operations, grants, resources, and endpoints. Clients do not submit
namespaces, Kubernetes kinds, Compose projects, or provider credentials.
Unsupported capabilities are rejected before infrastructure side effects.

Technology independence is a contract constraint, not a requirement to implement
multiple providers. The capability endpoint describes the selected Kubernetes
environment. Error responses use stable platform categories and redact backend
details while retaining an operation ID for authorized diagnosis.

## Infrastructure implementation

The Python application integrates directly with the selected infrastructure:

- Kubernetes/k3d for application services, scheduled components,
  Secrets, Services, and Ingress;
- PostgreSQL outside k3d for platform state and named-resource
  databases;
- operator-selected RustFS for named S3-compatible object storage;
- Caddy and Traefik for edge and cluster routing;
- Prometheus, Loki, Tempo, Alloy, Grafana, Alertmanager, and discovery
  files for observability;
- Keycloak through the generic OIDC boundary for authentication and
  machine identities.

There is no direct Docker application-workload adapter. Docker remains the host
runtime for the platform, identity, persistence, monitoring, and k3d containers.

## State and lifecycle

The catalog persists immutable UUIDs, desired revisions, operations,
grants, credentials, audit and AI records. Retirement removes
workloads and revokes access while retaining data and an encrypted
recovery point. Restoration uses the same UUID with fresh credentials.
Complete purge removes owned provider, catalog, audit, telemetry and
managed backup data; a durable operation waits for private host
verification before reporting completion. Name reuse creates a new
UUID only after purge succeeds. The
[lifecycle runbook](../operators/project-lifecycle.md) defines
previews, blockers, receipt lifetime and failure recovery.

An accepted operation means the desired state was recorded, not that the
workload is healthy. Operation results and live runtime observations remain
distinct. Drift is reported rather than silently repaired unless a future policy
explicitly enables reconciliation.

See the [current provisioning sequence](diagrams/provisioning.md),
[ApplicationSpec](application-contract.md),
[security model](../maintainers/delivery/history/security-design.md), and
[Phase 2C capability plan](../maintainers/delivery/history/phase-2c-platform-capabilities.md).

## Historical architecture work

ADRs and delivery plans preserve the decisions and proposals made at
their original dates. They are historical records. The implemented
reference is this architecture, the
[declaration contract](application-contract.md), the generated OpenAPI
schema and current operator runbooks. Proposed compute adapters and
service extraction in [evolution notes](evolution.md) are not
implemented.
