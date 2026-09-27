# Deployment and Installation

Status: current lab lifecycle procedures plus target installation/release drafts. Executable [bootstrap](../../scripts/up.sh), [platform Ansible](../../ansible/deploy.yml), and [watchdog/heartbeat playbooks](../../operations/watchdog/ansible/README.md) exist. Follow the [root setup guide](../../README.md) and [Ansible guide](../../ansible/README.md) for current commands.

The [backlog evidence](../04-development/delivery-backlog.md#evidence-conventions) records the inspected source baseline and passing local checks, including Compose configuration, shell syntax, and watchdog/heartbeat playbook syntax. No target-host deployment or live acceptance was performed in that assessment. The sequence below describes the target procedure; identity-provider setup, persistent workers, revision-aware reconciliation, and the complete acceptance flow remain implementation gaps.

## Current installation and lifecycle

**Validation:** the commands below were reviewed against the repository scripts. Shell syntax and Compose configuration checks passed in the [backlog evidence](../04-development/delivery-backlog.md#evidence-conventions); deployment, restart, and recreation were not executed for this documentation update.

Run from the repository root on the intended host, with the prerequisites in the [setup guide](../../README.md). For an Ansible installation, use a privileged shell in `/opt/developer-platform`; its configuration/runtime directories are root-only. Use a fresh trusted shell so previously exported settings do not override `.env`.

For a new local lab:

```bash
python3 scripts/init.py
python3 scripts/install-k3d.py
bash scripts/up.sh
```

`init.py` preserves an existing `.env`. Before public installation, configure domains, DNS, firewall, bind address, and non-overlapping network settings as described in the [host setup](../../README.md#deploy-to-the-existing-hetzner-host), or use the [Ansible deployment guide](../../ansible/README.md). The selected topology in [ADR-009](../03-decisions/ADR-009-edge-and-cluster-ingress.md) retains Caddy at the edge and Traefik inside k3d. The implementation uses one shared Docker network; segmentation remains separate target work.

Check startup using the [runbook commands](runbook.md#inspect-the-current-installation). `/healthz` checks only the API process; `/readyz` executes a SQL query and reads the `platform-system` namespace using the controller credential; it does not check all nodes or workloads. Neither proves an application's database write/read flow.

To stop services while retaining containers, cluster, and data:

```bash
docker compose stop
.runtime/bin/k3d cluster stop workloads
```

To start them again, or rebuild the API from updated sources:

```bash
bash scripts/up.sh
```

Bootstrap starts an existing cluster; it does not upgrade its Kubernetes image. It also does not reapply stored project specs automatically. Watchdog heartbeat delivery will stop during dependency downtime and can produce an external alert; no expiring maintenance-window feature exists.

### Recreate the workload cluster

This procedure removes Kubernetes workloads and custom cluster resources. First create and secure a [backup](backup-recovery.md#make-a-current-backup), preserve `.env`, record image versions, and save any manually managed manifests. The project catalog contains the latest `name/image/port/probe_profile` specs and lifecycle status, not revision history. Under [ADR-010](../03-decisions/ADR-010-single-environment-lab.md), new isolated installations are deferred. Use bounded checks on the existing lab and record version-migration validation that remains unverified; this procedure does not authorize creating another environment.

```bash
bash scripts/down.sh
# If changing the Kubernetes version, edit K3S_IMAGE in .env now.
bash scripts/up.sh
```

Without `--volumes`, teardown retains Compose service volumes, including PostgreSQL and the project catalog. Follow [reapply restored projects](backup-recovery.md#reapply-restored-projects), then verify workloads and application data. No SQL import is needed when the retained database volume is intact. Changing PostgreSQL major versions requires a separate migration or compatible logical restore; retaining its volume alone is not an upgrade procedure.

`bash scripts/down.sh --volumes` deletes persistent Compose service data as well as the cluster. It is a deliberate disposable-lab reset, not a recovery or routine upgrade step. Both teardown modes preserve `.env`, local backups, and installed tools.

Configure the [watchdog and heartbeat](../../operations/watchdog/ansible/README.md) and [off-host backup process](backup-recovery.md) separately. Installation alone does not verify notification receipt or recoverability.

## Target installation and release procedures

The remaining sections describe the intended architecture. Identity-provider setup, durable workers, revision history, scoped authorization, and operation IDs are not supplied by the current API.

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

Pause or safely drain jobs before incompatible schema changes, back up metadata, and define migration/rollback checks. ADR-010 currently defers any check requiring a new isolated environment; keep that acceptance open until the owner revises the constraint. After upgrading, test the API, authorization, providers, and a representative workflow. The rollback path must account for both software and metadata schema.

Release evidence includes artifact, spec/code revision, migrations, timestamp, executor, operation ID, and result. See [Runbook](runbook.md) and [Backup and recovery](backup-recovery.md).
