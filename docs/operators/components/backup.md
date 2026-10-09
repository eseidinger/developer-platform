# Backup automation

Status: optional current component.

The backup component captures platform PostgreSQL state and project credentials,
builds encrypted recovery bundles, uploads them to S3-compatible storage, reads
them back for verification, and records status for independent monitoring.

Use [Backup and recovery](../backup-and-recovery.md) for the canonical operator
workflow. The source-adjacent [backup reference](../../../operations/backup/README.md)
contains playbook variables, systemd units, test fixtures, retention mechanics,
and the detailed recovery-VM implementation.

Only a verified snapshot counts as a recovery point. A successful upload without
readback, an untested password, or a fresh dump that has never been restored does
not establish recoverability.
