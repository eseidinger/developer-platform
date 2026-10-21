# Monitoring maintenance

Status: current implementation guide.

Monitoring configuration spans Prometheus, Alertmanager, blackbox exporter,
Alloy, Tempo, the authenticated workload gateway/forwarder, Grafana, generated
application targets, private application metrics, PostgreSQL/native-store
collectors, AI telemetry, security-event metrics, and the external
heartbeat/watchdog boundary.

Run the local configuration and generator checks from the repository root:

```bash
python3 scripts/verify/observability/check-monitoring.py
python3 scripts/verify/observability/check-workload-logs.py
python3 scripts/verify/observability/check-application-metrics.py
python3 scripts/verify/observability/check-postgres-monitoring.py
python3 scripts/generate/generate-dashboards.py --check
```

The `check-*` scripts above use disposable Docker dependencies; they are fixture
checks, not read-only inspection of an installed platform. Dashboard generation
with `--check` is a source-only reproducibility check. Store/AI pipeline fixtures
and their exact dependencies are linked in the source-adjacent monitoring guide.

The source-adjacent [application monitoring README](../../infrastructure/monitoring/README.md)
documents target generation, rule files, fixtures, and implementation tests. The
[operator monitoring guide](../operators/monitoring.md) is canonical for signals,
alerts, dashboards, and live acceptance. The
[observability architecture](../architecture/observability.md) owns design and
failure-boundary rationale.

Any new signal must define ownership, bounded labels, secret/identity handling,
freshness semantics, expected failure behavior, and an acceptance procedure. A
local Prometheus assertion does not prove delivery through an external channel.
