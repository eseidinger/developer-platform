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
5. Check application data, permissions, ingress, and monitoring.

Losing the Kubernetes cluster therefore does not destroy the databases stored
outside it. The project list in PostgreSQL serves as the recovery catalog.

## Updates

Before changing versions, create a backup, validate images in a test installation,
and run all smoke and isolation tests. Images are versioned but not fully pinned
by digest; for reproducible releases, also pin digests and transitive Python
dependencies.


### Version refresh (September 2026)

Fresh deployments use PostgreSQL 18.6, Python 3.14.7, k3d 5.9.0, and k3s 1.36.4.
The PostgreSQL volume mounts at `/var/lib/postgresql`; the PostgreSQL 18 image
stores its data in `/var/lib/postgresql/18/docker`.

The Kubernetes Python client 36.0.3 and kube-state-metrics 2.20.0 are their latest
stable releases and target Kubernetes 1.36. The cluster version matches their target Kubernetes minor version.
The example image remains hashicorp/http-echo 1.0.0, its latest release.

Use the README quick start for a fresh installation. When recreating an existing
lab, run `bash scripts/down.sh --volumes` first, then set `K3S_IMAGE` in
`.env` to `rancher/k3s:v1.36.4-k3s1` before bootstrap. This discards existing lab
data. Updating `.env.example` alone does not change an existing `.env`, and
`up.sh` does not replace an existing cluster.

The host's minimum Python and Compose requirements describe script and configuration
compatibility, not pinned installations. The API container and CI use Python 3.14.7.
