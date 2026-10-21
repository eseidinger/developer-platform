# Observability architecture

This page owns observability design and failure-boundary rationale. For live
checks, alert handling, and dashboards, use the
[operator monitoring guide](../operators/monitoring.md). Implementation details
and tests belong in the [maintainer guide](../maintainers/monitoring.md).

Status: implemented lab signals plus target coverage. Source configuration is not deployment evidence; [current monitoring progress](../maintainers/delivery/backlog.md#current-monitoring-progress) records local preparation and operator-reported outcomes separately.

## Current signals and placement

| Signal | Implemented source/path | Limit |
|---|---|---|
| Host | node-exporter → Prometheus | No measured project/shared-service capacity breakdown |
| Kubernetes state and usage | kube-state-metrics via private NodePort 30090 plus TLS-verified kubelet cAdvisor → Prometheus | Bounded project-container CPU/memory series; request accounting and measured usage remain distinct |
| Application availability | Component-aware catalog → blackbox → Prometheus; Kubernetes readiness → kube-state-metrics | Protected public probes check the access boundary, not backend health; no independent external vantage point |
| Monitoring components | Prometheus and blackbox-exporter self-scrapes | Does not prove email delivery |
| Logs | Alloy reads Docker files and project pod logs through a dedicated read-only Kubernetes credential → Loki | Workload centralization keeps bounded JSON messages and operational envelopes; shared backends are operator-only |
| Views | Provisioned Grafana Prometheus/Loki/Tempo sources and operator dashboards | Owner-verified selected deployed views; project users use authorized fixed API reads |
| Traces | Bounded platform spans, private Alloy/Tempo and authenticated hosted OTLP through a Pod-local forwarder | Selected deployed trace/AI readback exists; full framework, outage, elapsed-retention and capacity acceptance remains open |
| Hosted metrics | Opt-in private scrape and fixed project HTTP reads, plus reviewed JVM/store workload families | Instrumentation is application-owned; complete framework/deployed coverage remains open |
| Alerts | Scrape failure, low disk, unavailable replicas, application failure/missing result/stale discovery → Alertmanager | Default receiver sends nothing; SMTP requires separate configuration |
| PostgreSQL and stores | Restricted PostgreSQL exporter and bounded native-store collectors → Prometheus | Aggregate operator statistics; provider health, last-good values and freshness are separate |
| Host health | systemd sender checks API SQL/Kubernetes access and Prometheus readiness → external watchdog | Does not directly inspect Docker, all nodes/workloads, Grafana, Loki or Alertmanager |
| Backup freshness | Optional scheduled runner → separately authenticated external backup channel | Independent of heartbeat; shares watchdog hosting/mail |

Prometheus retains seven days or 4 GB, whichever limit is reached first; Loki has
seven-day compactor retention and persistent storage configured. Alloy explicitly
collects attributed project pod logs over the verified Kubernetes API. Loki has
authentication disabled and no published host port; shared-backend access is
administrative. Project users read centralized logs only through the authorized
Platform API's fixed project selector, never an unfiltered Grafana/Loki link.

[ADR-020](decisions/ADR-020-generic-hosted-application-integration.md)
accepts seven-day centralized workload-log retention for the initial
cross-project integration profile. PLAN-017 now implements attributed workload
collection and authorized reads; deployed neutral probes/readiness and immediate
central correlation reads passed in
[EV-46](../operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026).
Post-retirement/restart log readback and elapsed retention remain acceptance
work. Metrics contain
only Public or Internal data. Workload logs may contain Internal operational data
and explicitly approved Confidential correlation values, but no customer
payloads or Restricted values.

Central storage and alerting are outside k3d but share its host failure domain. The external PHP/MySQL watchdog is independently hosted. Its optional fixed HTTPS GET checks status codes, not the application content contract. The systemd component sends heartbeats only on successful readiness checks; it is not a local notification service.

[ADR-014](decisions/ADR-014-catalog-availability-monitoring.md) records catalog membership, bounded profiles, monitoring-only reconciliation and retirement semantics. [Application monitoring](../../infrastructure/monitoring/README.md) supplies configuration and verification procedures. Discovery retains failed applications and excludes only explicitly retired catalog entries. The thread does not repair workloads.

[ADR-015](decisions/ADR-015-verified-backup-bundles.md) records capture-time freshness and separate backup notifications. Under [ADR-011](decisions/ADR-011-watchdog-monitoring-boundary.md), the monitoring chain ends at the external watchdog; silent hosting/scheduler/mail failure is accepted for the lab. Maintenance windows are not implemented.

## Target coverage and project views

PostgreSQL exporter metrics, native-store collection and workload CPU/memory
scrapes are implemented. Attributed centralized operational logs are implemented.
[Phase 4](../maintainers/delivery/plans/phase-4-tracing-and-dashboards.md)
has source for bounded platform and opt-in hosted-application tracing, private
Tempo collection, operator dashboards, and opt-in private hosted metrics. Phase 4
was accepted for lab sequencing under its recorded exception; remaining checks
are in Phase 10. Selected live AI trace/metric readback and owner-verified
dashboards are recorded in the [AI evidence](../../infrastructure/monitoring/AI.md#deployed-smoke-check-october-17-2026). Application spans require verified workload
provenance; raw trace search remains operator-only.
The [Phase 4 tracing decision](decisions/ADR-021-phase-4-tracing-boundary.md)
fixes Tempo/Alloy placement, workload authentication, retention and resource
limits, and the bounded project-read contract. Spring Boot, Quarkus and FastAPI
dashboard templates require matching application instrumentation; source
templates alone do not prove populated panels.

Operators should see host, Docker, cluster, database, certificates, storage, jobs and monitoring. Developers should see only authorized applications and logs/health/metrics. Shared dashboard links cannot enforce this boundary. Introduce server-side authorization before exposing those views.

Probe labels use project/application names, default environment, component,
namespace and URL. Platform-derived revision/operation pod annotations become
non-indexed log metadata. Application-supplied opaque correlation keys live only
in JSON record bodies, not metric or stream-index labels. Bounded Quarkus/Spring
JSON messages and operational envelopes are centrally retained; unknown JSON
fields are discarded and plain-text logs remain kubelet-only. Known credential
patterns receive best-effort redaction. Applications must keep secrets out of
messages and supply appropriately classified opaque correlation identifiers.
See the [implemented formats and limits](../../infrastructure/monitoring/WORKLOAD-TELEMETRY.md#central-workload-logs-and-correlation).

## Status and operational evidence

The current catalog stores `empty`, `provisioning`, `applied`, `failed` or `retired`; it does not transition with ongoing workload health. Authorized operation reads now provide a live readiness snapshot, separate from the apply outcome, including desired/ready counts, deployment/active images and diagnostic reason. This is an on-demand observation, not a persisted catalog health transition or continuous observer; Kubernetes/API errors are reported as unknown rather than healthy.

Selected heartbeat, SMTP, scrape-rule and backup DOWN/UP notifications have operator-reported receipt in the backlog. Application probe fixtures do not establish live application-rule delivery or complete host/cluster failure acceptance. Continue controlled checks on the existing lab under [ADR-010](decisions/ADR-010-single-environment-lab.md); no duplicate installation is required.

Phase 5 AI reads authorized telemetry alongside deployment history and redacted changes, separating observations, gaps and hypotheses. [ADR-005](decisions/ADR-005-observability-watchdog.md) explains target failure boundaries; [Monitoring](../operators/monitoring.md) covers current checks and remaining acceptance.
