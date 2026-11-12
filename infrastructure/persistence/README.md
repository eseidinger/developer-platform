# Persistence services

Run Compose from the repository root. `compose.yaml` owns the shared PostgreSQL
server and pgAdmin console; `shared-stores.yaml` owns optional RustFS object
storage.

- `Dockerfile` builds the reviewed AGE, pgvector, TimescaleDB, pgmq, and
  pg_duckdb sources in a separate stage. The runtime installs pinned PostGIS
  packages and copies the other installed extension files from the build stage.
- `console/` owns pgAdmin authentication and session policy.
- `compatibility/` contains a disposable PostgreSQL coexistence/restore harness,
  its build image, and dated compatibility evidence. Preserve historical records
  when changing the harness; they describe the source tested on that date.

Build dependencies use explicit APT versions in both PostgreSQL Dockerfiles.
Review these pins together when updating the base image or dependencies, and
verify package availability and dependency resolution. Upstream repositories may
remove superseded versions, requiring a reviewed pin update.

The compatibility harness creates temporary databases, restarts its own server,
and tests logical restore. Its AGE OID repair applies only to disposable fixture
databases. Never run it inside a live PostgreSQL container.

PLAN-040's component check runs every six-extension subset in a disposable
PostgreSQL image, then exercises managed roles and representative SQL:

```bash
NAMED_POSTGRES_IMAGE=developer-platform-postgres:plan040 \
  platform/app/.venv/bin/python \
  scripts/tests/components/stores/verify-postgres-extension-expansion.py
```

`pg_duckdb` is preloaded but its execution role is granted only to writers of
resources that select it. External file and network access, including S3, is
disabled at server startup. The image limits DuckDB to 128 MiB and two threads
per connection. Review these controls with host capacity before changing them.

The same-major image rollback rehearsal uses a separate disposable volume:

```bash
platform/app/.venv/bin/python \
  scripts/tests/components/stores/verify-postgres-image-rollback.py
```

It validates old → new → old with existing pgvector data and no newly selected
extensions. Once new extension data is written, the old image lacks the
required binaries; recovery then requires the verified pre-upgrade backup and
the new image rather than a simple image switch.

Run static checks from the repository root:

```bash
hadolint infrastructure/persistence/Dockerfile \
  infrastructure/persistence/compatibility/Dockerfile
yamllint infrastructure/persistence
shellcheck infrastructure/persistence/*.sh \
  infrastructure/persistence/compatibility/*.sh
ruff check infrastructure/persistence
ruff format --check infrastructure/persistence
docker compose --profile '*' config --quiet
```
