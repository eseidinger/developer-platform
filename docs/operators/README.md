# Platform operator guide

Status: current. Last reviewed October 9, 2026.

Use this section to install and administer the shared Developer Platform. It
covers the host, Docker services, k3d/Kubernetes, PostgreSQL, identity, edge,
observability, backups, and independent watchdog components.

## Start here

- [Infrastructure inventory](infrastructure.md)
- [Local installation](install-local.md)
- [Remote installation](install-remote.md)
- [Identity and access](identity-and-access.md)
- [Lifecycle and upgrades](lifecycle.md)
- [Monitoring and alerting](monitoring.md)
- [Backup and recovery](backup-and-recovery.md)
- [Incident runbooks](runbooks/README.md)
- [Fresh-install acceptance](validation/acceptance.md)
- [Playbook component matrix](validation/playbook-component-matrix.md)

## Optional operational components

The platform can combine four source-adjacent components, each with a different
responsibility:

- [Alertmanager](components/alertmanager.md) routes Prometheus alerts.
- [Backup automation](components/backup.md) creates and verifies encrypted
  recovery bundles.
- [Heartbeat](components/heartbeat.md) reports platform readiness to an external
  boundary.
- [Watchdog](components/watchdog.md) detects stale heartbeat and backup signals
  outside the platform host.

The topology is a single failure domain and is intended for a controlled lab.
Do not infer production-grade availability or isolation from successful local
acceptance.
