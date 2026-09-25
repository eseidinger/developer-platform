# Requirements

Status: consolidated requirements; prioritization and evidence are drafts. Mandatory requirements describe target acceptance, not current implementation.

| ID | Requirement | Stage | Acceptance evidence |
|---|---|---|---|
| F-01 | Manage projects and environments with stable identity and ownership | MVP | Create/read/update and cross-project access tests |
| F-02 | Declaratively deploy an OCI image, HTTP endpoint, configuration, and health check | MVP | UC-01 without manually creating backend artifacts |
| F-03 | Provision a PostgreSQL database and dedicated workload role; bind a secret | MVP | Write/read data; no secrets in API status or logs |
| F-04 | Expose desired and observed state and asynchronous operations | MVP | Restart a worker during provisioning and retain a traceable state |
| F-05 | Support updates, restarts, and controlled removal | MVP | Repeatable operations; persistent data is retained |
| F-06 | Associate logs, basic metrics, health, and deployment revisions | MVP | Locate a failed rollout through the API and monitoring |
| F-07 | Support a shared contract across Kubernetes and Docker providers | Phase 2 | Same spec on both providers; no backend fields in the core contract |
| F-08 | Check environment capabilities and reject unsupported requirements | MVP core, extended in Phase 2 | Reject autoscaling on an unsuitable environment without side effects |
| F-09 | Authorize and audit separate human database access | Phase 3 | Tunnel/database login distinct from application login; revocation test |
| F-10 | Offer a portal, templates, and OIDC integration for hosted applications | Phase 3 | Template-to-healthy-application flow with separate platform/application permissions |
| F-11 | Generate AI diagnoses through read-only platform tools | Phase 4 | Incident diagnosis with evidence; deny access to another project's context |
| F-12 | Execute AI changes through the Platform API using an approved plan | Phase 4 | No mutation without valid approval for the exact revision and target |
| N-01 | Keep the public Platform API technology-independent | Confirmed requirement | Contract review and F-07 |
| N-02 | Make provisioning idempotent and resumable after partial failures | MVP | Database creation succeeds, deployment fails, retry creates no duplicates |
| N-03 | Enforce project/environment boundaries server-side | MVP | Negative tests for resources, logs, secrets, jobs, and database access |
| N-04 | Reference, protect, and redact secrets | MVP | Spec/audit/log inspection; rotation followed by reconnection |
| N-05 | Make infrastructure and recovery reproducible | MVP | Rebuild and isolated restore from an external backup |
| N-06 | Keep monitoring available during workload-cluster failure; detect host failure externally | MVP | k3d failure and separate host/heartbeat failure tests |
| N-07 | Keep single-host operation within available resources | MVP | Load measurement including log growth, database, and reserve; no swap/disk exhaustion |
| N-08 | Audit changes, role assignments, and provider operations | MVP | Correlate actor, target, revision, timestamp, result, and operation ID |

## Boundaries and open operational targets

The hybrid installation is a single-host lab with a shared failure domain. Multiple Kubernetes nodes in Docker do not provide host-level high availability. Namespaces and Docker networks alone do not guarantee strong tenant isolation.

Availability, p95 provisioning time, API latency, log retention, RPO, RTO, and concurrent application count remain to be defined. First measure baselines under representative load; do not promise unsupported SLAs.

Multi-cluster operation, automatic multi-node HA, a broad data-service catalog, complex autoscaling, and unattended AI remediation are outside the MVP. See the [development plan](../04-development/development-plan.md) for phases and dependencies.
