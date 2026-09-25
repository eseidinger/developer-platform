# Backup and Recovery

Status: operational draft. No backup or restore has been executed as part of preparing this documentation. Recoverability is a central operational acceptance criterion for the single-host architecture.

## Backup scope

| Data | Backup approach | Restore considerations |
|---|---|---|
| Project databases | Consistent PostgreSQL backups | Engine compatibility, extensions, roles/grants |
| Platform metadata | Database backup including revisions and provider mappings | Restart must not duplicate resources |
| Database roles and permissions | Separately saved administrative state | Restore owners and default privileges |
| Identity-provider state | Appropriate database/configuration backup | Include clients, identities, and key material |
| Secrets/keys | Separate encrypted backup | Access must remain possible during platform failure |
| Infrastructure/routing configuration | Versioned repository plus external configuration | No secrets in Git |
| Application volumes | Consistent application-specific backups | Cannot be reconstructed from image or spec |
| Dashboards/alert rules | Versioned configuration | Telemetry history has separate retention |

A volume on the same host is not an external backup. Backups require separate credentials and protection against accidental overwrite or deletion.

## Policy before operational acceptance

RPO, RTO, frequency, retention, encryption, storage location, and ownership remain to be defined. Daily logical database backups are a possible lab starting point; they do not automatically satisfy shorter RPO targets. For stronger requirements, evaluate base backups, WAL archiving, and point-in-time recovery.

Monitoring checks backup age and outcome. Recoverability is demonstrated only through restore verification.

## Restore procedure

1. Establish incident scope, the latest consistent backup, and acceptable data loss.
2. Build a new isolated target environment; do not overwrite production volumes.
3. Make keys/secrets available through the designated emergency access path.
4. Restore PostgreSQL foundations, roles/extensions, and required databases in the appropriate order.
5. Restore the identity provider and platform metadata. Keep workers paused initially.
6. Inventory provider resources and reconcile them with restored IDs/revisions; resolve orphaned or newer resources manually.
7. Start compatible application revisions; verify data, permissions, and health.
8. Switch routing only after acceptance, then resume workers deliberately.
9. Record the actual data recovery point, RPO/RTO, deviations, and follow-up work.

Restoring one project must not overwrite others. Database state, application version, and schema must be compatible. Retained resources from deletion operations remain inventoried.

## Exercise and evidence

Perform a complete recovery using test data into an empty target environment. Verify roles, grant separation, secret bindings, and a write/read operation. Record backup ID, versions, start/end times, data checks, and result.

[Deployment](deployment.md), [Runbook](runbook.md), [ADR-003](../03-decisions/ADR-003-postgresql-provisioning.md).
