# Observability Architecture

Status: implemented lab signals plus target coverage. Source configuration is not deployment evidence; [current monitoring progress](../04-development/delivery-backlog.md#current-monitoring-progress) records local preparation and operator-reported outcomes separately.

## Current signals and placement

| Signal | Implemented source/path | Limit |
|---|---|---|
| Host | node-exporter → Prometheus | No measured project/shared-service capacity breakdown |
| Kubernetes object state | kube-state-metrics via private NodePort 30090 → Prometheus | No pod/container CPU or memory usage scrape |
| Application availability | Catalog → file discovery → blackbox exporter → Prometheus | Root-path status/content from the platform host, not an independent external network |
| Monitoring components | Prometheus and blackbox-exporter self-scrapes | Does not prove email delivery |
| Logs | Alloy reads host Docker JSON log files → Loki | No explicit k3d application log collection or project/environment attribution |
| Views | Grafana Prometheus/Loki data sources | No provisioned dashboards or scoped developer views |
| Alerts | Scrape failure, low disk, unavailable replicas, application failure/missing result/stale discovery → Alertmanager | Default receiver sends nothing; SMTP requires separate configuration |
| Host health | systemd sender checks API SQL/Kubernetes access and Prometheus readiness → external watchdog | Does not directly inspect Docker, all nodes/workloads, Grafana, Loki or Alertmanager |
| Backup freshness | Optional scheduled runner → separately authenticated external backup channel | Independent of heartbeat; shares watchdog hosting/mail |

Prometheus retains seven days or 4 GB, whichever limit is reached first; Loki has seven-day retention configured. Alloy's host file collector depends on Docker JSON log files and does not collect pod logs inside k3d explicitly. Loki has authentication disabled. Access to shared backends is administrative, with no platform-enforced tenant filters.

Central storage and alerting are outside k3d but share its host failure domain. The external PHP/MySQL watchdog is independently hosted. Its optional fixed HTTPS GET checks status codes, not the application content contract. The systemd component sends heartbeats only on successful readiness checks; it is not a local notification service.

[ADR-014](../03-decisions/ADR-014-catalog-availability-monitoring.md) records catalog membership, bounded profiles, monitoring-only reconciliation and retirement semantics. [Application monitoring](../../infrastructure/monitoring/README.md) supplies configuration and verification procedures. Discovery retains failed applications and excludes only explicitly retired catalog entries. The thread does not repair workloads.

[ADR-015](../03-decisions/ADR-015-verified-backup-bundles.md) records capture-time freshness and separate backup notifications. Under [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md), the monitoring chain ends at the external watchdog; silent hosting/scheduler/mail failure is accepted for the lab. Maintenance windows are not implemented.

## Target coverage and project views

PostgreSQL exporter metrics, application request/error/latency signals, workload resource usage, attributed Kubernetes logs and traces remain future work. Proposed OpenTelemetry/Tempo integration is not installed. Durable jobs/revisions must exist before exposing their telemetry.

Operators should see host, Docker, cluster, database, certificates, storage, jobs and monitoring. Developers should see only authorized applications and logs/health/metrics. Shared dashboard links cannot enforce this boundary. Introduce server-side authorization before exposing those views.

Target telemetry uses stable project, environment and application IDs plus deployment revision, operation ID, and infrastructure resource IDs. Propagate correlation context across API handling, durable operation execution, and infrastructure calls inside the Python application. The API exposes health, error, latency, dependency, saturation, and operation-age signals; dashboards distinguish request, policy/coordination, and infrastructure-execution failures. Current probe labels use project/application name, namespace and URL; there are no environment/revision/operation IDs. Avoid unbounded request or operation IDs in metric labels; use structured logs or trace context for them.

## Status and operational evidence

The current catalog stores `provisioning`, `applied`, `failed` or `retired`; it does not transition with ongoing workload health. Authorized operation reads now provide a live readiness snapshot, separate from the apply outcome, including desired/ready counts, deployment/active images and diagnostic reason. This is an on-demand observation, not a persisted catalog health transition or continuous observer; Kubernetes/API errors are reported as unknown rather than healthy.

Selected heartbeat, SMTP, scrape-rule and backup DOWN/UP notifications have operator-reported receipt in the backlog. Application probe fixtures do not establish live application-rule delivery or complete host/cluster failure acceptance. Continue controlled checks on the existing lab under [ADR-010](../03-decisions/ADR-010-single-environment-lab.md); no duplicate installation is required.

Later AI reads authorized telemetry alongside deployment history and redacted changes, separating observations, gaps and hypotheses. [ADR-005](../03-decisions/ADR-005-observability-watchdog.md) explains target failure boundaries; [Monitoring](../05-operations/monitoring.md) covers current checks and remaining acceptance.
