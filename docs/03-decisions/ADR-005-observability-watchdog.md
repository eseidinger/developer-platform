# ADR-005 – Monitoring Across Failure Boundaries

Created: September 25, 2026. Status: **Proposed**; infrastructure and watchdog implementation scope established.

## Context

Monitoring inside the workload cluster disappears when that cluster fails. Monitoring containers on the same host cannot reliably detect complete host loss. Independent PHP/MySQL web hosting is available.

## Proposed decision

Collectors remain close to monitored components; Prometheus, Grafana, Loki, and Alertmanager run outside k3d. A systemd watchdog monitors Docker and central services. An external PHP/MySQL system receives authenticated heartbeats and checks them using an independent scheduler.

Keep the external watchdog small: last receipt time, probe result, state changes, and alert/recovery delivery. It is not a second telemetry backend.

## Alternatives

Keeping everything in the cluster is simple but shares its failure domain. A host-only watchdog detects Docker failures, not host loss. An external monitoring service could replace PHP/MySQL; selection and cost remain undecided.

## Consequences

The three layers have distinct responsibilities. Test the heartbeat, check scheduler, and notification channel separately. Tokens, TLS, deduplication, maintenance windows, and alert resolution are operational responsibilities.

## Validation

Stop the workload cluster, simulate a Docker service failure, and stop heartbeats: the appropriate independent layer must respond. Then verify recovery notifications and alert resolution.

Details: [Observability](../02-architecture/observability.md), [Monitoring](../05-operations/monitoring.md).
