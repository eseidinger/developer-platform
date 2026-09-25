# Deployment and Installation

Status: **operational draft** for the hybrid installation. No installation or executable deployment scripts are present here. Add commands from the actual implementation; this procedure does not claim an existing CLI contract.

## Define the installation profile first

Required inputs include host access, DNS/domains, registry, approved software versions, persistent volume paths, private network ranges, secret storage, external backup storage, OIDC configuration, and watchdog/alert recipients. Agree on RPO/RTO and retention before production-like acceptance.

The profile pins images and charts immutably or uses controlled versions. Credentials remain outside the repository.

## Bootstrap sequence

1. Prepare the host, storage, time synchronization, administrative access, and firewall.
2. Configure Docker, networks, and persistent PostgreSQL; prepare database/role management and backups.
3. Start observability and the host watchdog; test the external watchdog and alert channel.
4. Configure the k3d workload cluster, ingress, and collectors; test PostgreSQL connectivity.
5. Initialize the identity provider and platform metadata; start the API/worker with restricted provider credentials.
6. Verify edge routes and TLS before opening application environments.
7. Deploy a sample project through the normal platform path; test health, database writes, logs, and permissions.
8. Save installation parameters, revision, resource inventory, and evidence.

Host/foundation installation and project provisioning are separate. A project request must not trigger host or cluster installation.

## Application release

Builds and tests produce an OCI artifact. CI submits its immutable identity and desired spec revision to the platform. The reconciler creates a plan, checks capabilities, and performs the rollout. Acceptance depends on observed revision and health.

Schema migrations belong to the application and use separate migration permissions. Prefer compatible expand/contract steps over an unverified simultaneous schema/code change.

Rollback restores a known workload and configuration revision. It does not automatically roll back the database schema. Verify image, configuration, and schema compatibility before rollback.

## Platform upgrade

Pause or safely drain jobs before incompatible schema changes, back up metadata, and test migration in a non-production environment first. After upgrading, test the API, authorization, providers, and a representative workflow. The rollback path must account for both software and metadata schema.

Release evidence includes artifact, spec/code revision, migrations, timestamp, executor, operation ID, and result. See [Runbook](runbook.md) and [Backup and recovery](backup-recovery.md).
