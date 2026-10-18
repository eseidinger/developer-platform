# Docker-based Developer Platform Lab

The Developer Platform is a single-host lab for deploying containerized
applications through a platform API instead of managing Kubernetes and PostgreSQL
resources directly. Docker Compose runs shared services and k3d/k3s runs
application workloads.

```text
Internet → Caddy (TLS)
              ├─ Platform API and Keycloak
              └─ k3d → Traefik → project namespaces
                                    └─ explicit bindings → named data stores

Prometheus, Grafana, Loki, Tempo, Alloy, Alertmanager, backups, and an external
watchdog support operations around the platform.
```

## Features

- Declarative, versioned application deployments through a REST API and CLI.
- Multi-service applications and scheduled components on Kubernetes.
- Independent named PostgreSQL resources, explicit component bindings, human
  access leases, and pgAdmin SSO; optional RustFS S3, OpenSearch, Qdrant, and
  dedicated Neo4j Community providers.
- OIDC authentication, platform-owned grants, revocable CI credentials, and
  redacted audit events.
- Durable deployment operations, revision-aware updates, diagnostics, and
  explicit retirement.
- Restricted workloads, project quotas, egress policy, monitoring, encrypted
  backups, and independent availability signals.
- Opt-in application metrics and traces, operator dashboards, and bounded
  project AI assistance with reviewed, approved rollback proposals.

This remains a single-host lab and is not a hardened multi-tenant production
platform. See the [product overview](docs/product/overview.md) for its scope and
the [architecture overview](docs/architecture/README.md) for its boundaries.

## Quick start

Requirements: Docker Engine with Compose 2.20.3 or newer, Python 3.10 or newer,
Bash, `setfacl` (the Linux `acl` package), loopback-mount tools,
kubectl 1.36.x (1.35.x–1.37.x supported), and internet access. Suggested
capacity is 16 vCPUs and 32 GB RAM.

```bash
python3 scripts/init.py
python3 scripts/install-k3d.py
sudo bash scripts/prepare-tempo-storage.sh
docker compose up -d postgres keycloak-db-init keycloak proxy
# Create the initial Keycloak user and put its immutable ID in
# PLATFORM_BOOTSTRAP_SUBJECT in .env before starting the API.
bash scripts/up.sh
# Obtain and export a short-lived administrator PLATFORM_ACCESS_TOKEN first.
python3 scripts/smoke.py
```

`init.py` creates a private `.env` without replacing existing values. The smoke
test intentionally retains its `smoke` project. The Python API and CLI packages
require Python 3.12 or newer when run outside their containers. AI runs additionally
require configured provider credentials, processing eligibility, and project
classification. For prerequisites, identity
bootstrap, checks, and cleanup, follow the complete
[local installation guide](docs/operators/install-local.md).

## Documentation

Start at the [documentation home](docs/README.md), or go directly to the journey
that matches your work:

- [Deploy an application](docs/developers/README.md)
- [Operate the platform](docs/operators/README.md)
- [Change the platform](docs/maintainers/README.md)
- [Understand the architecture](docs/architecture/README.md)
- [Review product scope and direction](docs/product/overview.md)

The detailed [Ansible](ansible/README.md), [platform](platform/README.md), and
[operational component](operations/README.md) READMEs remain source-adjacent
implementation references. User and operator workflows are canonical under
`docs/`.

## Repository validation

```bash
docker compose config --quiet
uv sync --project platform/app
uv run --project platform/app python -m unittest discover -s platform/app/tests -v
python3 -m unittest discover -s ansible/tests -v
python3 scripts/check-monitoring.py
python3 scripts/check-doc-links.py
python3 -m unittest discover -s operations/backup/tests -v
uv run --project platform/app python -m compileall -q platform/app/src/app scripts operations
bash -n scripts/up.sh scripts/down.sh
```

Live smoke and capability-specific recovery/failure drills are documented in
[platform acceptance](docs/operators/validation/acceptance.md). They can alter a
running lab and must be run only in the environment and scope described there.
The [documentation review](docs/maintainers/documentation-review.md) records
legacy database helpers that require adaptation to the current binding contract.
