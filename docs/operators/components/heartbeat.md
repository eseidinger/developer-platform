# Platform heartbeat

Status: optional current component.

The heartbeat sender runs on the platform host. It checks Platform API dependency
readiness and Prometheus readiness, then sends an authenticated signal to the
external watchdog. It does not establish application data integrity or
Alertmanager delivery.

Deploy and exercise it with the source-adjacent
[heartbeat guide](../../../operations/heartbeat/README.md). Verify the systemd
timer and service, sender connectivity, and both outage and recovery observation
at the watchdog. Keep tokens out of command output and incident records.
