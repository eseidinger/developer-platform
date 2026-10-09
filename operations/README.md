# Operational tooling

This README maps source directories. Operator workflows and the explanation of
how these components cross failure boundaries are canonical in the
[operator component guide](../docs/operators/components/README.md).

| Directory | Responsibility |
| --- | --- |
| [watchdog](watchdog/README.md) | External PHP/MySQL monitoring, backup signals, and outage/recovery notifications |
| [alertmanager](alertmanager/README.md) | Inventory-based authenticated SMTP configuration and email delivery checks |
| [heartbeat](heartbeat/README.md) | Platform health checks and authenticated heartbeat sender |
| [backup](backup/README.md) | PostgreSQL dumps, encrypted S3 backups, retention, and recovery helpers |

Each component owns its deployment files and scripts. Run documented commands from the repository root. Platform bootstrap remains in [ansible](../ansible/README.md); operational procedures remain in the [operator runbooks](../docs/operators/runbooks/README.md).

This layout changes repository paths only. Installed systemd unit names, host configuration paths, and watchdog URLs remain unchanged.
