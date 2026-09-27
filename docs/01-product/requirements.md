# Requirements

Status: consolidated requirements; prioritization and evidence are drafts. Mandatory requirements describe target acceptance, not current implementation.

## Delivery terminology

**MVP (minimum viable product) means Phase 1**, including all three ordered gates: 1A operational protection, 1B accountable access, and 1C durable single-application lifecycle. It is not a separate stage before the numbered phases. See the [Phase 1 gates](../04-development/phase-1-foundation.md#ordered-work-packages-and-acceptance-gates).

The delivery phase identifies when the listed acceptance evidence is first required. Requirements continue to apply in later phases and to new endpoints/providers. “Confirmed requirement” describes decision status, not a delivery phase; N-01 is a confirmed constraint across all phases, with two-provider evidence due in Phase 2.

Phase 1 acceptance must pass before advancing to Phase 2. Later hardening or extensions do not postpone the Phase 1 minimum:

| Requirement | Phase 1 (MVP) minimum | Phase 2 extension |
|---|---|---|
| F-04 / N-02 | Persist desired state and traceable operations; observe readiness and resume interrupted provisioning without duplicates or data loss | Harden concurrency and drift recovery; add retained-revision recovery and provider parity |
| F-06 | Diagnose a failed rollout through authorized basic logs, metrics, health and revision context | Add full log search/follow and retention, resource comparisons and capacity views |
| F-08 | Validate the supported single-image profile and reject unsupported capabilities before side effects | Publish environment/provider capability profiles and verify the portable contract on Kubernetes and Docker |

Phase 3 adds developer experience and access extensions; Phase 4 adds AI assistance and controlled actions. The full delivery backlog spans these phases and includes explicitly deferred work, so completing the MVP does not mean completing every backlog story.

| ID | Requirement | Delivery phase | Acceptance evidence |
|---|---|---|---|
| F-01 | Manage projects and environments with stable identity and ownership | Phase 1 (MVP) | Create/read/update and cross-project access tests |
| F-02 | Declaratively deploy an OCI image, HTTP endpoint, configuration, and health check | Phase 1 (MVP) | UC-01 without manually creating backend artifacts |
| F-03 | Provision a PostgreSQL database and dedicated workload role; bind a secret | Phase 1 (MVP) | Write/read data; no secrets in API status or logs |
| F-04 | Expose desired and observed state and asynchronous operations | Phase 1 (MVP) | Restart a worker during provisioning and retain a traceable state |
| F-05 | Support updates, restarts, and controlled removal | Phase 1 (MVP) | Repeatable operations; persistent data is retained |
| F-06 | Associate logs, basic metrics, health, and deployment revisions | Phase 1 (MVP) | Locate a failed rollout through the API and monitoring |
| F-07 | Support a shared contract across Kubernetes and Docker providers | Phase 2 | Same spec on both providers; no backend fields in the core contract |
| F-08 | Check environment capabilities and reject unsupported requirements | Phase 1 (MVP) core; Phase 2 extension | Reject autoscaling on an unsuitable environment without side effects |
| F-09 | Authorize and audit separate human database access | Phase 3 | Tunnel/database login distinct from application login; revocation test |
| F-10 | Offer a portal, templates, and OIDC integration for hosted applications | Phase 3 | Template-to-healthy-application flow with separate platform/application permissions |
| F-11 | Generate AI diagnoses through read-only platform tools | Phase 4 | Incident diagnosis with evidence; deny access to another project's context |
| F-12 | Execute AI changes through the Platform API using an approved plan | Phase 4 | No mutation without valid approval for the exact revision and target |
| N-01 | Keep the public Platform API technology-independent | All phases; portability verified in Phase 2 | Contract review and F-07 |
| N-02 | Make provisioning idempotent and resumable after partial failures | Phase 1 (MVP) | Database creation succeeds, deployment fails, retry creates no duplicates |
| N-03 | Enforce project/environment boundaries server-side | Phase 1 (MVP) | Negative tests for resources, logs, secrets, jobs, and database access |
| N-04 | Reference, protect, and redact secrets | Phase 1 (MVP) | Spec/audit/log inspection; rotation followed by reconnection |
| N-05 | Make infrastructure and recovery reproducible | Phase 1 (MVP) | Rebuild and isolated restore from an external backup |
| N-06 | Keep monitoring available during workload-cluster failure; detect host failure externally | Phase 1 (MVP) | k3d failure and separate host/heartbeat failure tests |
| N-07 | Keep single-host operation within available resources | Phase 1 (MVP) | Load measurement including log growth, database, and reserve; no swap/disk exhaustion |
| N-08 | Audit changes, role assignments, and provider operations | Phase 1 (MVP) | Correlate actor, target, revision, timestamp, result, and operation ID |

## Delivery acceptance

The [delivery backlog](../04-development/delivery-backlog.md) retains detailed DEV/OPS acceptance criteria. The [development plan crosswalk](../04-development/development-plan.md#backlog-delivery-commitments) assigns them to phases, including security-event notifications and project retirement as explicit extensions of these broad requirements. Single-image slices do not close deferred multi-component criteria.

## Boundaries and open operational targets

The hybrid installation is a single-host lab with a shared failure domain. Multiple Kubernetes nodes in Docker do not provide host-level high availability. Namespaces and Docker networks alone do not guarantee strong tenant isolation.

Availability, p95 provisioning time, API latency and concurrent application count remain to be defined. The owner selected a 24-hour RPO and four-hour RTO, twelve-hour backups and 14 daily / 8 weekly / 6 monthly retention points; these are targets, not measured guarantees. Prometheus and Loki currently use seven-day retention; a project log-access/retention contract remains open. The lab initial response target is 24 hours with one responder. See [backup policy evidence](../04-development/delivery-backlog.md#current-backup-and-recovery-progress) and [alert ownership](../05-operations/monitoring.md#alert-process). Measure representative baselines before promising SLAs.

Multi-cluster operation, automatic multi-node HA, a broad data-service catalog, complex autoscaling, and unattended AI remediation are outside Phase 1 (MVP). See the [development plan](../04-development/development-plan.md) for phases and dependencies.
