# Phase 1 – Foundation and Usable Vertical Slice

Status: planned; existing Python/Kubernetes functionality is reported only. Covers [F-01 through F-06, F-08, and N-02 through N-08](../01-product/requirements.md).

## Goal

Create, update, observe, and deliberately remove a web application with PostgreSQL on the existing hybrid host using a minimal API/CLI.

## Work packages

1. Inventory the actual repository, Python entry points, configuration, and existing resources. Reproduce the working flow.
2. Define a reproducible hybrid profile with separate stacks, k3d, PostgreSQL outside k3d, edge routing, and persistent storage.
3. Introduce or verify authentication and basic project/environment authorization.
4. Implement database/role, secret binding, workload, route, and health as a resumable vertical slice. Use stable resource IDs and minimally separated provider ports from the start.
5. Integrate basic telemetry, external backups, the systemd watchdog, and the external watchdog.
6. Refine operational instructions using a real installation; document versions and environment parameters.

## Acceptance

- Deploy a sample application into a fresh environment and write/read data.
- Repeat the same spec without creating another database or workload.
- Trigger a deployment failure after database creation; retry resumes and preserves data.
- Reject unauthorized access to a second project.
- Updates and removal expose correct status; retain the database according to policy.
- Restore a backup into an isolated environment and run the application against it.
- A k3d failure and a missing external heartbeat produce their respective alerts.

Use test resources for these checks; do not intentionally lose production data.

## Outside this phase

A complete portal, broad data-service catalog, HA PostgreSQL, multi-cluster support, AI, and an implementation-language rewrite. Quarkus may serve as a sample application without rebuilding the control plane.

Dependencies: [Deployment](../05-operations/deployment.md), [Monitoring](../05-operations/monitoring.md), [Backup and recovery](../05-operations/backup-recovery.md).
