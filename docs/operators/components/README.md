# Operational components

Status: current optional-component index.

These optional components extend the core platform across different failure
boundaries:

| Component | Responsibility | Failure boundary |
|---|---|---|
| [Alertmanager](alertmanager.md) | Route Prometheus alerts to receivers | Platform host |
| [Backup](backup.md) | Capture, encrypt, verify, retain, and restore state | Platform host plus off-host storage |
| [Heartbeat](heartbeat.md) | Send dependency readiness to an external receiver | Platform host to external host |
| [Watchdog](watchdog.md) | Detect stale heartbeat and backup status | Independent web host/database |

Deploy only the components needed by the installation profile, but do not count a
component as independent evidence when it shares the failure boundary being
tested.
