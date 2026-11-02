# Operational components

Status: current optional-component index.

These optional components extend the core platform across different failure
boundaries:

- **Component:** [Alertmanager](alertmanager.md)
  - **Responsibility:** Route Prometheus alerts to receivers
  - **Failure boundary:** Platform host
- **Component:** [Backup](backup.md)
  - **Responsibility:** Capture, encrypt, verify, retain, and restore state
  - **Failure boundary:** Platform host plus off-host storage
- **Component:** [Heartbeat](heartbeat.md)
  - **Responsibility:** Send dependency readiness to an external receiver
  - **Failure boundary:** Platform host to external host
- **Component:** [Watchdog](watchdog.md)
  - **Responsibility:** Detect stale heartbeat and backup status
  - **Failure boundary:** Independent web host/database

Deploy only the components needed by the installation profile, but do not count
a component as independent evidence when it shares the failure boundary being
tested.
