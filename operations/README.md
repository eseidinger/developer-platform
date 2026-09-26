# Operational tooling

| Directory | Responsibility |
| --- | --- |
| [watchdog](watchdog/README.md) | External PHP/MySQL monitoring, backup signals, and outage/recovery notifications |
| [heartbeat](heartbeat/README.md) | Platform health checks and authenticated heartbeat sender |
| [backup](backup/README.md) | PostgreSQL dumps, encrypted S3 backups, retention, and recovery helpers |

Each component owns its deployment files and scripts. Run documented commands from the repository root. Platform bootstrap remains in [ansible](../ansible/README.md); operational procedures remain in [docs/05-operations](../docs/05-operations/runbook.md).

This layout changes repository paths only. Installed systemd unit names, host configuration paths, and watchdog URLs remain unchanged.
