# Backup and recovery

## PostgreSQL

`bash scripts/backup.sh` writes a compressed pg_dumpall dump to
`.runtime/backups/`, publishing it atomically only after the dump succeeds.
It includes roles, password hashes, and all databases. The local dump is not an
offsite backup. After each run, encrypt it and copy it to another host or storage
system, with limited retention and regular restore tests.

Also back up `.env` (especially `DATABASE_KEY`), Caddy data, and, if needed,
Grafana configuration with encryption. Dumps do not include container images.
Applications must store persistent application data exclusively in PostgreSQL;
PVCs are not allowed by the initial project contract.

## Restore on a new host

1. Provide the same configuration and the backed-up `.env`.
2. Start only PostgreSQL: `docker compose up -d postgres`.
3. Import the dump into the empty target instance:
   `gzip -dc backup.sql.gz | docker compose exec -T postgres psql -U postgres`.
   The existing postgres role and platform database may cause already-exists
   messages during the pg_dumpall import; investigate any other errors.
   Never restore blindly over a running instance that already contains data.
4. Run `bash scripts/up.sh`. Retrieve stored projects using GET /projects
   and reapply each project's spec using PUT /projects/{name}.
   Kubernetes Secrets and workloads are recreated using the same `DATABASE_KEY`.
5. Check application data, permissions, ingress, and the watchdog.

Losing the Kubernetes cluster therefore does not destroy the databases stored
outside it. The project list in PostgreSQL serves as the recovery catalog.

## Watchdog

See [Watchdog](../watchdog/README.md). The systemd timer checks API readiness
(database + Kubernetes) and Prometheus before sending a heartbeat.
A failed timer or host results in an overdue heartbeat at the external watchdog.
If the watchdog cron job fails, the status page also reports unavailable.

## Updates

Before changing versions, create a backup, validate images in a test installation,
and run all smoke and isolation tests. Images are versioned but not fully pinned
by digest; for reproducible releases, also pin digests and transitive Python
dependencies.
