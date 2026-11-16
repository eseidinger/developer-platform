# Persistence services

Run Compose from the repository root. `compose.yaml` owns the shared PostgreSQL
server and pgAdmin console; `shared-stores.yaml` owns optional RustFS object
storage. Pull the published PostgreSQL image before starting Compose.

- The separate `platform-postgres` repository builds the reviewed AGE, pgvector,
  TimescaleDB, pgmq, and pg_duckdb sources in a separate stage. The runtime
  installs pinned PostGIS packages and copies the other installed extension
  files from the build stage.
- `console/` owns pgAdmin authentication and session policy.

Build dependencies use explicit APT versions in the image Dockerfile. Review
these pins together when updating the base image or dependencies, and verify
package availability and dependency resolution. Upstream repositories may remove
superseded versions, requiring a reviewed pin update.

Pull the image and run PLAN-040's component check from the repository root. It
runs every six-extension subset in a disposable PostgreSQL image, then exercises
managed roles and representative SQL:

```bash
docker pull eseidinger/platform-postgres:18.6-extensions-20261112
NAMED_POSTGRES_IMAGE=eseidinger/platform-postgres:18.6-extensions-20261112 \
  platform/app/.venv/bin/python \
  scripts/tests/components/stores/verify-postgres-extension-expansion.py
```

`pg_duckdb` is preloaded but its execution role is granted only to writers of
resources that select it. External file and network access, including S3, is
disabled at server startup. The image limits DuckDB to 128 MiB and two threads
per connection. Review these controls with host capacity before changing them.

Once new extension data is written, the old image lacks the required binaries;
recovery then requires the verified pre-upgrade backup and the new image rather
than a simple image switch.

Run static checks from the repository root:

```bash
yamllint infrastructure/persistence
shellcheck infrastructure/persistence/*.sh
ruff check infrastructure/persistence
ruff format --check infrastructure/persistence
docker compose --profile '*' config --quiet
```
