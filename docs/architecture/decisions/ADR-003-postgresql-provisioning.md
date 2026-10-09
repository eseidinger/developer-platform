# ADR-003 – Shared PostgreSQL Service with Separate Identities

Created: September 25, 2026. Status: **Proposed**.
Source inspection confirms [database/login provisioning and credential derivation](../../../platform/app/main.py) and [Kubernetes Secret bindings](../../../platform/app/manifests.py). The runtime login currently owns its database; separate migration/owner and human identities remain proposed. See the [backlog evidence](../../maintainers/delivery/backlog.md#evidence-conventions) for local verification and outstanding live isolation, rotation, and restore acceptance. This source evidence does not accept the proposed decision.

## Context

Projects need simple relational persistence. A dedicated database server for each application increases resource use and operational effort. Developers also need interactive access without sharing the workload identity.

## Proposed decision

A centrally operated PostgreSQL server resides outside the workload cluster. Each logical database resource belongs to one project/environment; the MVP typically has one database per project/environment. Additional resources receive stable IDs so multiple databases remain possible later.

Separate runtime, migration/owner, and human roles. The platform manages database creation and access; applications manage their schema migrations. Platform state and project data use separate databases/roles.

Human access starts with a separate role and controlled tunnel; time-limited credentials are an optional later extension. PostgreSQL is not generally exposed to the public internet.

## Alternatives

One instance per project provides better resource isolation but costs more. A schema per project saves resources but requires stricter namespace/privilege discipline. Managed PostgreSQL and operator-based provisioning remain future providers.

Sharing application credentials with people is simple but prevents clear attribution and independent revocation.

## Consequences and security details

A shared server shares an engine version, maintenance, and failure domain. Storage declarations are not hard per-database quotas without additional enforcement. Administrative roles remain with the provisioner; runtime roles receive neither superuser privileges nor blanket access to other databases.

Handle CONNECT privileges, PUBLIC defaults, schema and table/sequence permissions, and default privileges for future objects explicitly. A `read` grant alone is not a complete SQL implementation.

Retention is the default deletion behavior; permanent data deletion is a separate lifecycle step. Backups include databases and the roles/grants needed for recovery.

## Validation

Verify isolation between two projects, separate runtime/human logins, rotation, database creation with retries, and restore including roles.

Details: [ApplicationSpec](../application-contract.md), [Backup and recovery](../../operators/backup-and-recovery.md), [Phase 3](../../maintainers/delivery/plans/phase-3-developer-experience.md).
