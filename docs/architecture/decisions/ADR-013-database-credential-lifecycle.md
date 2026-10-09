# ADR-013 – Deterministic Project Credentials and Retained SQL Data

Recorded: September 27, 2026. Status: **Implemented baseline; owner acceptance of this record not recorded**. ADR-003's proposed separation of runtime, owner/migration and human identities remains outstanding.

## Context

Repeat PUT and cluster recreation must reconnect workloads to an existing database without deleting data. The current catalog stores specs/status, not independently versioned credential objects.

## Implemented choice

For a project, the database and login name are `project_` plus the project name with hyphens replaced by underscores. The password is the hexadecimal HMAC-SHA256 of the project name under `DATABASE_KEY`. The API creates a missing login with NOSUPERUSER/NOCREATEDB/NOCREATEROLE, creates a missing database owned by it, and revokes PUBLIC database privileges. Existing role passwords are left unchanged.

The generated `database` Kubernetes Secret supplies `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD`. PostgreSQL lives outside k3d with a persistent Compose volume. Workload retirement retains database, login and catalog; there is no API data-purge operation. The same login owns the database and runs application SQL; separate migration and human identities do not exist.

## Alternatives and consequences

Random stored credentials with versioned secret objects would support independent rotation and revocation but add state and recovery requirements. Separate runtime/owner/human roles would reduce runtime authority and improve attribution; this remains the target in ADR-003.

Deterministic derivation keeps repeat provisioning stable while the key is unchanged. The key is a platform-wide recovery dependency: losing it prevents re-derivation, and compromising it exposes every derived project credential. Protect it with independently recoverable encrypted configuration.

Changing only `DATABASE_KEY` and repeating PUT rewrites Kubernetes credentials but does not rotate existing SQL passwords. Coordinate SQL role changes, Secret updates and successful workload reconnection. Restoring SQL without the original key/configuration can produce the same mismatch. Shared PostgreSQL also shares version, capacity and failure domain; database separation is not a hard storage quota or transport encryption.

## Evidence and evolution

Source: [password/database provisioning](../../../platform/app/main.py), [Secret generation](../../../platform/app/manifests.py), [PostgreSQL placement](../../../persistence/compose.yaml). [Backup and recovery](../../operators/backup-and-recovery.md) covers preservation of the original configuration; [the runbook](../../operators/runbooks/security.md#compromised-credential-or-access-revocation) covers current rotation constraints.

DEV-003-T02, DEV-010-T01 and PLAN-008 remain open for versioned rotation/adoption and separated identities. Validate live role/Secret rotation and denied foreign database access before claiming those outcomes. Revisit before individual human database access or important application data relies on this baseline.
