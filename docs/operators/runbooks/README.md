# Operations runbooks

Status: current. Last reviewed October 9, 2026.

Choose the failure boundary that best matches the symptom:

- [Application runbooks](application.md): failed provisioning, rollout health,
  restart, deployment demonstration, and application availability.
- [Platform runbooks](platform.md): installation health, PostgreSQL, Docker,
  Kubernetes, capacity, networking policy, heartbeat, disk, and backups.
- [Security runbooks](security.md): compromised credentials and access
  revocation.

Start with [inspect the current installation](platform.md#inspect-the-current-installation)
when the boundary is unclear. Record the time, host, code revision, affected
project, latest declaration, observed symptoms, and recovery result.

The procedures were reviewed against source. The
[delivery evidence register](../../maintainers/delivery/backlog.md#evidence-conventions)
records which checks have actually run and their environment limits.
