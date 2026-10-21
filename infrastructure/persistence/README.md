# Persistence services

Run Compose from the repository root. `compose.yaml` owns the shared PostgreSQL
server and pgAdmin console; `shared-stores.yaml` owns optional store services
and the Neo4j controller.

- `Dockerfile` builds the reviewed AGE and pgvector extensions in a separate
  stage, then copies their installed files into the PostgreSQL runtime image.
- `console/` owns pgAdmin authentication and session policy.
- `opensearch-bootstrap.sh` initializes only a confirmed absent security
  catalog. Existing broken catalogs require operator repair and are never
  overwritten.
- `opensearch-dashboards.yaml` configures the scoped search console.
- `neo4j/` owns the Neo4j image and JVM exporter configuration.
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

Run static checks from the repository root:

```bash
hadolint infrastructure/persistence/Dockerfile \
  infrastructure/persistence/compatibility/Dockerfile \
  infrastructure/persistence/neo4j/Dockerfile
yamllint infrastructure/persistence
shellcheck infrastructure/persistence/*.sh \
  infrastructure/persistence/compatibility/*.sh
ruff check infrastructure/persistence
ruff format --check infrastructure/persistence
docker compose --profile '*' config --quiet
```
