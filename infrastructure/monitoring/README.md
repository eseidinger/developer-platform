# Monitoring configuration

This directory owns monitoring service configuration, Prometheus rules and their
fixtures, and generated Grafana dashboards. Use the
[operator monitoring guide](../../docs/operators/monitoring.md) for live
operations and the
[maintainer monitoring guide](../../docs/maintainers/monitoring.md) for
implementation ownership.

## Configuration layout

- **`compose.yaml`:** Monitoring services, private networking, mounts, and
  resource budgets.
- **`prometheus.yaml`:** Scrape discovery, authentication, limits, and metric
  allowlists.
- **`alerts.yaml`, `capacity-rules.yaml`:** Alerting and capacity recording
  rules.
- **`tests/`:** Prometheus rule fixtures, separate from live acceptance.
- **`config.alloy`:** Log ingestion and bounded OTLP trace and metric pipelines.
- **`loki.yaml`, `tempo.yaml`:** Log and trace storage and retention settings.
- **`blackbox.yaml`:** Bounded public-route probe profiles.
- **`postgres-queries.yaml`:** Fixed aggregate SQL for the restricted exporter.
- **`alertmanager.yaml`:** Local receiver defaults; delivery requires operator
  configuration.
- **`datasources.yaml`, `dashboards.yaml`:** Grafana provisioning.
- **`dashboards/`:** Generated JSON; edit the dashboard generator, then
  regenerate.

The platform API publishes application targets from PostgreSQL to a shared
`monitoring_discovery` volume. Prometheus discovers and probes these targets
without a restart. The default Alertmanager `local-only` receiver sends no
email.

## Contracts and procedures

- [Application monitoring](APPLICATIONS.md): targets, public-boundary probes,
  lifecycle, security-event alerts, and retirement.
- [Workload telemetry](WORKLOAD-TELEMETRY.md): hosted trace metadata and
  structured log contracts, privacy limits, correlation, and retained reads.
- [Capacity and stores](CAPACITY-AND-STORES.md): resource accounting, PostgreSQL
  monitoring, and provider performance signals.
- [Platform traces](TRACING.md): private trace bootstrap and bounded storage.
- [Platform AI observability](AI.md): OpenLIT integration, direct metrics, and
  limits.
- [Validation](VALIDATION.md): local fixtures, deployment preparation, and
  remaining live acceptance requirements.
- [Verification history](VERIFICATION-HISTORY.md): dated deployment observations
  and references to their private evidence.

## Local quality checks

Run these from the repository root after installing `requirements.txt`:

```bash
yamllint infrastructure
python3 scripts/generate/generate-dashboards.py --check
python3 scripts/checks/check-doc-links.py
docker compose --profile '*' config --quiet
```

Use the pinned service images for native Alloy and Caddy format checks and the
Prometheus rule fixtures. The [validation guide](VALIDATION.md) describes
commands and the boundary between disposable local checks and live operational
acceptance.
