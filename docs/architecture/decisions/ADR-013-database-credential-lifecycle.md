# ADR-013 – Deterministic Project Credentials and Retained SQL Data

Recorded: September 27, 2026. Status: **Implemented baseline; owner acceptance of this record not recorded**. ADR-003's proposed runtime/owner separation remains outstanding; separate read-only human identity is implemented in source but not deployed-accepted.

## Implementation status note — October 18, 2026

The deterministic project-wide database/Secret model below is a historical
baseline. Current named resources and explicit bindings use independent credential
generations: application rotation every 30 days with at most one-hour overlap,
and 24-hour human leases. Resource retirement retains data; confirmed purge waits
for verified off-host intent. See [current store operations](../../operators/data-stores.md).
This implementation update does not approve or rewrite the original record.

## Context

Repeat PUT and cluster recreation must reconnect workloads to an existing database without deleting data. The current catalog stores specs/status, not independently versioned credential objects.

## Implemented choice

For a project, the database and login name are `project_` plus the project name with hyphens replaced by underscores. The password is the hexadecimal HMAC-SHA256 of the project name under `DATABASE_KEY`. The API creates a missing login with NOSUPERUSER/NOCREATEDB/NOCREATEROLE, creates a missing database owned by it, and revokes PUBLIC database privileges. Existing role passwords are left unchanged.

The generated `database` Kubernetes Secret supplies `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD`. PostgreSQL lives outside k3d with a persistent Compose volume. Workload retirement retains database, workload login and catalog; operator-controlled permanent purge is a separate lifecycle action. The same workload login owns the database and runs application SQL; no separate migration role exists. Distinct read-only human roles and a controlled tunnel are implemented in source, with deployed acceptance pending.

## Alternatives and consequences

Random stored credentials with versioned secret objects would support independent rotation and revocation but add state and recovery requirements. Separate runtime/owner/human roles would reduce runtime authority and improve attribution; this remains the target in ADR-003.

Deterministic derivation keeps repeat provisioning stable while the key is unchanged. The key is a platform-wide recovery dependency: losing it prevents re-derivation, and compromising it exposes every derived project credential. Protect it with independently recoverable encrypted configuration.

Changing only `DATABASE_KEY` and repeating PUT rewrites Kubernetes credentials but does not rotate existing SQL passwords. Coordinate SQL role changes, Secret updates and successful workload reconnection. Restoring SQL without the original key/configuration can produce the same mismatch. Shared PostgreSQL also shares version, capacity and failure domain; database separation is not a hard storage quota or transport encryption.

## Evidence and evolution

Source: [password/database provisioning](../../../platform/app/src/app/main.py), [Secret generation](../../../platform/app/src/app/manifests.py), [PostgreSQL placement](../../../persistence/compose.yaml). [Backup and recovery](../../operators/backup-and-recovery.md) covers preservation of the original configuration; [the runbook](../../operators/runbooks/security.md#compromised-credential-or-access-revocation) covers current rotation constraints.

DEV-003-T02 and DEV-010-T01 remain open for versioned workload rotation/adoption and owner separation. PLAN-008 remains open for deployed human-role, tunnel, foreign-project denial, and revocation acceptance. Validate live role/Secret rotation and denied foreign database access before claiming those outcomes.
