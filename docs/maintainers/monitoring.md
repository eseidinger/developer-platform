# Monitoring maintenance

Status: current implementation guide.

Monitoring configuration spans Prometheus, Alertmanager, blackbox exporter,
Alloy, Grafana, generated application targets, security-event metrics, and the
external heartbeat/watchdog boundary.

Run the local configuration and generator checks from the repository root:

```bash
python3 scripts/check-monitoring.py
```

The source-adjacent [application monitoring README](../../infrastructure/monitoring/README.md)
documents target generation, rule files, fixtures, and implementation tests. The
[operator monitoring guide](../operators/monitoring.md) is canonical for signals,
alerts, dashboards, and live acceptance. The
[observability architecture](../architecture/observability.md) owns design and
failure-boundary rationale.

Any new signal must define ownership, bounded labels, secret/identity handling,
freshness semantics, expected failure behavior, and an acceptance procedure. A
local Prometheus assertion does not prove delivery through an external channel.
