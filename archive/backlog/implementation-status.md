# Backlog implementation status

Assessment date: 2026-09-22. Scope: the source, configuration, scripts, and tests
in this checkout, assessed against [the backlog](backlog.md). This is a repository
review, not a verification of a running installation. Existing live-test scripts
and previously documented observations are evidence of intended checks, not new
test results from this assessment.

## Status definitions

- **Implemented:** all story acceptance criteria are supported.
- **Partial:** a relevant capability exists, but some acceptance criteria or the
  intended user's access to it are missing.
- **Not implemented:** the requested workflow is absent; adjacent infrastructure
  alone does not satisfy the story.

**Summary:** 0 implemented, 12 partial, and 7 not implemented. The platform is an
admin-operated lab for trusted workloads. All project API operations use one
shared administrator token; none currently provides developer-specific access.
The counts below describe functional coverage, not a percentage of work completed.

Watchdog update: the recreated PHP/MySQL watchdog, host heartbeat sender, systemd
units, and local test tooling are now included in this assessment. This adds
implementation coverage to OPS-007, which remains partial; the story totals are
unchanged. Public installation and actual email receipt are not established by
the repository evidence.

## Developer stories

| Story | Status | Current implementation | Remaining work |
| --- | --- | --- | --- |
| DEV-001 — Multiple components | Partial | A project creates one Deployment, Service, and Ingress. Image and a single port are configurable; replicas are fixed at one. Namespace-local communication is allowed. | Separate application/component model; commands, ports, replicas, internal service discovery across components, independent updates, and component-specific outcomes. |
| DEV-002 — Environment configuration | Not implemented | The project schema accepts only name, image, and port. Database connection variables are injected automatically. | Component environment CRUD, readback, validation, authorized access, and visibility into configuration activation and required rollouts. |
| DEV-003 — Secrets | Partial | A generated Kubernetes Secret supplies database credentials; ordinary project responses omit them. Project endpoints require the admin token. | User-managed secrets, per-component assignment and authorization, safe replacement/removal, redaction guarantees, and rollout adoption tracking. There is no individual credential rotation workflow. |
| DEV-004 — Application logs | Not implemented | Loki, Alloy, and Grafana exist, but Alloy reads host Docker JSON logs. Kubernetes workload logs inside k3d are not explicitly collected or labeled by project/component/instance. Loki retention is configured to seven days. | Workload log ingestion, source metadata, filtering and follow access, retained logs after instance termination, project authorization, and user-visible retention. Loki has authentication disabled and must remain behind a controlled access boundary. |
| DEV-005 — Application resources | Partial | GET /projects lists stored specs and provisioning status. Administrators can inspect Kubernetes resources directly. kube-state-metrics provides object-state metrics. | Authorized resource inventory, attached service relationships, actual component CPU/memory metrics, comparison with requests/limits/quotas, and explicit missing/stale metric handling. |
| DEV-006 — Deployment health | Partial | Provisioning records provisioning/applied/failed. TCP readiness/liveness probes exist; the smoke script checks rollout separately. Documentation explicitly says applied does not mean ready. | API-visible continuous rollout health, desired/ready counts, observed image version, and actionable failed/stalled rollout reasons. Kubernetes events/pod reads are not in the provisioner's current RBAC. |
| DEV-007 — Failed-change recovery | Partial | Repeated PUT reapplies resources under a database advisory lock. Existing databases and credentials are preserved while DATABASE_KEY is unchanged. The latest desired spec is stored. | Retained revisions and selection, recovery rollout status, dependency checks including unavailable secret versions, and explicit migration/data rollback boundaries. PUT overwrites the previous stored spec; retries are manual and there is no background reconciliation. |
| DEV-008 — Scaling | Not implemented | Manifests fix replicas at one, CPU at 100m/500m request/limit, and memory at 128Mi/256Mi. Kubernetes quotas provide a fixed upper bound. | Per-component replica and resource settings, quota validation with useful errors, and host-capacity/scheduling diagnostics. |
| DEV-009 — Connectivity | Partial | Every project gets a hostname and public ingress. Caddy authorizes on-demand certificates for applied projects. Fixed policy permits same-namespace traffic, DNS, and PostgreSQL. | Private-only components, endpoint selection and TLS status, declared external destinations, operator policy decisions, and rejection explanations. Real DNS/ACME TLS is documented as not locally verified. |
| DEV-010 — Data services | Partial | Provisioning creates a database/login per project, revokes PUBLIC database access, and injects connection settings. PostgreSQL data lives outside k3d; repeated PUT does not delete it. An isolation script checks foreign database access denial. | Authorized component assignment, project database availability reporting, and a developer recovery request/operator response workflow. API readiness checks the platform database, not each project's credentials and data service. |
| DEV-011 — Application removal | Not implemented | No application or project deletion API exists. The teardown script operates on the entire lab. | Application-scoped preview, explicit confirmation, resource cleanup, completion/partial-failure tracking, and persistent-data retention by default. |

Developer implementation evidence:

- [API and storage](../platform/app/main.py): Project schema, admin dependency,
  provisioning, status persistence, database roles, and certificate authorization.
- [Generated manifests](../platform/app/manifests.py): fixed workload settings,
  Secrets, probes, networking, quotas, and public ingress.
- [Platform guide](../platform/README.md): API contract and manual operator workflows.
- [Log collector](../infrastructure/monitoring/config.alloy),
  [Loki configuration](../infrastructure/monitoring/loki.yaml), and
  [Kubernetes metrics](../infrastructure/kubernetes/metrics.yaml): collection scope.
- [Provisioner permissions](../infrastructure/kubernetes/controller.yaml),
  [smoke checks](../scripts/smoke.py), and [isolation checks](../scripts/isolation.py).

## Operator stories

| Story | Status | Current implementation | Remaining work |
| --- | --- | --- | --- |
| OPS-001 — Security audits | Partial | Security settings and network policies are declared in manifests and inspectable with administrator tools. | Individual actor attribution; durable timestamped action/target/outcome events; filtered export; redaction; retention and audit access controls. Generic application error logs are not an audit trail. |
| OPS-002 — Security notifications | Not implemented | Prometheus and Alertmanager are wired together with grouping and repeat intervals, but rules cover infrastructure rather than security. The local-only receiver has no delivery integration. The external watchdog implements availability-change email, not security-event notifications. | Authentication/access/privileged-change event signals and configurable rules, contextual notifications linked to evidence, real destinations, delivery tests/failure visibility, and security-appropriate grouping. |
| OPS-003 — Capacity monitoring | Partial | node-exporter supplies host metrics, kube-state-metrics supplies object state, and a low-disk alert exists. Grafana has data sources. Shared service memory limits are defined in Compose. | Project/container actual usage, shared-service usage breakdown, requested capacity versus host capacity, quota visibility, dashboards, stale-data handling, CPU/memory thresholds, and unschedulable workload reporting. No dashboards are provisioned. |
| OPS-004 — Identity and access | Not implemented | One bearer token authorizes administrative access to every project; monitoring uses separate administrator access. Workloads do not receive Kubernetes API tokens. | Individual identities, memberships, viewer/developer/operator permissions, authorization across all data surfaces, prompt revocation, and audited permission changes. |
| OPS-005 — Policies and quotas | Partial | Each namespace receives fixed quotas, a LimitRange, restricted Pod Security enforcement, and a NetworkPolicy; generated workloads are hardened. | Configurable per-project policy, useful violation responses, impact previews, and admission decisions informed by host capacity. Network policy convergence can briefly permit new-pod egress; this is not hostile-tenant isolation. |
| OPS-006 — Backup and restore | Partial | backup.sh atomically publishes a local compressed pg_dumpall with private file permissions; this includes project data, roles, and platform state. Operations documentation covers manual restore and separately saving configuration/secrets. | Scheduling, automated encrypted off-host storage, retention/access policy, configuration/secret backup automation, failure/overdue alerts, recovery targets, and recorded restoration exercises. No automated restore test is present. |
| OPS-007 — Availability monitoring | Partial | Existing health checks and alerts are supplemented by a systemd heartbeat sender checking local API readiness and Prometheus. The independent PHP/MySQL watchdog detects stale heartbeats, optionally checks one fixed HTTPS target with HEAD, records 30-day check history, and attempts outage/recovery email with retries after failed mail handoff. Its public status page reports stale cron checks as unavailable. | Verify public deployment, timer/cron operation, and actual email receipt; add reliable end-to-end application checks, remaining shared-service coverage, and affected-project context. Alertmanager still has no delivery receiver, and its pipeline is not exercised by the host heartbeat. Watchdog cron/hosting failure needs independently delivered notification, not just a 503 status page. Backup freshness is not monitored. |
| OPS-008 — Project decommissioning | Not implemented | down.sh removes the entire cluster/Compose stack and optionally all service volumes. Provisioner RBAC has no delete verbs. | Per-project inventory/preview, retention decisions, explicit destructive confirmation, access/credential revocation, narrowly authorized cleanup, retryable partial failures, and audit records of deleted/retained resources. |

Operator implementation evidence:

- [API](../platform/app/main.py), [workload policies](../platform/app/manifests.py),
  and [architecture limits](../docs/architecture.md).
- [Prometheus targets](../infrastructure/monitoring/prometheus.yaml),
  [alert rules](../infrastructure/monitoring/alerts.yaml),
  [notification routing](../infrastructure/monitoring/alertmanager.yaml), and
  [monitoring services](../infrastructure/monitoring/compose.yaml).
- [Backup script](../scripts/backup.sh), [recovery procedure](../docs/operations.md),
  [database service](../persistence/compose.yaml), and [lab teardown](../scripts/down.sh).
- [Watchdog installation](../watchdog/README.md), [host sender](../watchdog/scripts/heartbeat.py),
  [service](../watchdog/systemd/platform-heartbeat.service),
  [timer](../watchdog/systemd/platform-heartbeat.timer),
  [external cron](../watchdog/cron.php), and [public status](../watchdog/public/index.php).

## Verification limits and cross-cutting gaps

The [unit tests](../tests/test_manifests.py) cover name validation, namespace/network
manifest structure, workload hardening, and selected quota settings. The smoke
script covers unauthenticated rejection, readiness, repeat provisioning, rollout,
and HTTP routing. The isolation script checks selected database and network
boundaries after a convergence delay. None establishes complete coverage of a
backlog story; this review did not run live checks or a recovery exercise.

Watchdog evidence includes [freshness boundary tests](../watchdog/tests/watchdog.php) and a
[disposable PHP/MariaDB test](../watchdog/scripts/test-watchdog.py) covering missing-token
rejection, method validation, throttling, heartbeat expiry, recovery, and stale
cron status. The disposable test substitutes `/bin/true` for mail delivery and
disables the optional HTTPS probe. It does not verify real mail receipt,
mail-failure retries, wrong-token rejection, the host sender/systemd installation,
or a public probe. CI includes PHP syntax/freshness checks; it does not run the
disposable integration test. These tests were inspected, not rerun for this
documentation update.

The main cross-cutting gaps are developer authorization, a multi-component domain
model, observed runtime status, and durable operation/audit history. Manual
administrator access does not complete a developer workflow. Existing monitoring
infrastructure and watchdog code do not establish deployed notification delivery
or tenant-safe queries.

See the [implementation plan](implementation-plan.md) for the proposed sequence
and milestone exit criteria. Update this assessment when an item ships, citing
the implementation and verification evidence before marking a story implemented.
