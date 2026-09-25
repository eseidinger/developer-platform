# Observability Architecture

Status: design draft; installed dashboards and alert rules have not been verified.

## Signals and placement

| Signal | Source | Proposed destination |
|---|---|---|
| Host and containers | node-exporter, container metrics | Prometheus |
| Kubernetes | kube-state-metrics, node/workload metrics | Prometheus outside k3d |
| PostgreSQL | Database exporter and host metrics | Prometheus |
| Logs | Collector with project/environment attribution | Loki |
| Traces, later | OpenTelemetry instrumentation/collector | Optional Tempo |
| Alerts | Prometheus rules | Alertmanager and designated recipients |
| Platform domain status | Reconciler, jobs, health checks | Platform API and dashboards |

Collectors run near their sources; central storage and alerting are outside the workload cluster. On a single host, they still depend on that host. A host watchdog outside Docker and an independent PHP/MySQL watchdog complement one another.

## Platform and project views

Operators see the host, Docker, cluster, database, certificates, storage, jobs, and monitoring itself. Developers see only authorized applications and their logs, health, versions, and metrics. Links to shared dashboards do not replace data-access enforcement.

Telemetry uses stable project, environment, and application IDs, deployment revisions, and operation IDs. Metric labels exclude unbounded user/request IDs. Structured logs and trace context identify individual requests.

## Domain status

`RUNNING` requires observed readiness of the desired revision. A started container alone is insufficient. Missing telemetry is marked unknown or stale, not healthy. Provider state, application health, and monitoring availability remain distinguishable.

MVP signals include request errors and latency, resource consumption, database connections, free disk space, backup age, and job failures. Automatic performance diagnosis is not an MVP feature.

## Monitoring itself and AI context

An authenticated heartbeat from the platform host reaches independent web hosting. Its independent scheduler detects overdue heartbeats and sends a deduplicated alert and recovery notification. A heartbeat proves only that the sender functions; additional service probes are needed.

Later, AI reads telemetry alongside deployment history and redacted configuration changes. Results distinguish observations, data gaps, and hypotheses.

[ADR-005](../03-decisions/ADR-005-observability-watchdog.md) explains the failure boundaries. [Monitoring](../05-operations/monitoring.md) covers operational checks and alert procedures.
