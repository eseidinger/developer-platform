# Docker-based Developer Platform Lab

The Developer Platform is a single-host lab for deploying containerized
applications through a platform API instead of managing Kubernetes and PostgreSQL
resources directly. Docker Compose runs shared services and k3d/k3s runs
application workloads.

```text
Internet → Caddy (TLS)
              ├─ Platform API and Keycloak
              └─ k3d → Traefik → project namespaces
                                    └─ shared PostgreSQL

Prometheus, Grafana, Loki, Alloy, Alertmanager, backups, and an external
watchdog support operations around the platform.
```

## Features

- Declarative, versioned application deployments through a REST API and CLI.
- Multi-service applications and scheduled components on Kubernetes.
- Per-project PostgreSQL databases and credentials.
- OIDC authentication, platform-owned grants, revocable CI credentials, and
  redacted audit events.
- Durable deployment operations, revision-aware updates, diagnostics, and
  explicit retirement.
- Restricted workloads, project quotas, egress policy, monitoring, encrypted
  backups, and independent availability signals.

This remains a single-host lab and is not a hardened multi-tenant production
platform. See the [product overview](docs/product/overview.md) for its scope and
the [architecture overview](docs/architecture/README.md) for its boundaries.

## Quick start

Requirements: Docker Engine with Compose 2.20.3 or newer, Python 3.10 or newer,
Bash, kubectl 1.36.x (1.35.x–1.37.x supported), and internet access. Suggested
capacity is 16 vCPUs and 32 GB RAM.

```bash
python3 scripts/init.py
python3 scripts/install-k3d.py
# Create the initial Keycloak user and put its immutable ID in
# PLATFORM_BOOTSTRAP_SUBJECT in .env.
docker compose up -d postgres keycloak-db-init keycloak proxy
bash scripts/up.sh
python3 scripts/smoke.py
```

`init.py` creates a private `.env` without replacing existing values. The smoke
test intentionally retains its `smoke` project. For prerequisites, identity
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
python3 -m pip install -r platform/requirements-dev.txt
python3 -m unittest discover -s platform/tests -v
python3 -m unittest discover -s ansible/tests -v
python3 scripts/check-monitoring.py
python3 scripts/check-doc-links.py
python3 -m unittest discover -s operations/backup/tests -v
python3 -m compileall -q platform scripts operations
bash -n scripts/up.sh scripts/down.sh
```

Live smoke, isolation, recovery, and failure drills are documented in
[platform acceptance](docs/operators/validation/acceptance.md). They can alter a
running lab and must be run only in the environment and scope described there.
