# Platform implementation reference

The platform is one Python/FastAPI control plane, with a React portal at `/`
and a separate `devplat` CLI. Canonical workflows are in the
[developer guide](../docs/developers/README.md) and
[operator guide](../docs/operators/README.md). This page describes source ownership
and local maintainer commands.

## Runtime and state

Docker Compose runs the API, telemetry gateway, Keycloak, PostgreSQL, edge and
monitoring. Kubernetes/k3d runs application services/scheduled components and the
shared hosted-access authorizers with per-policy browser proxies. The API uses
in-process workers with durable
PostgreSQL records for deployments, hosted access and named stores.

The catalog stores project/application identities, grants, revisions, operations,
credential metadata, store resources and grants, AI runs/proposals, audit and
retirement records. Kubernetes stores application secret values. Store credentials
are derived from protected operator keys and lease identities, then injected only
into explicitly bound components. Keycloak owns identity-provider accounts and
clients. See the [platform database model](../docs/platform-model/platform-database.md).

Stores have an independent lifecycle. The default provider is PostgreSQL;
operator-selected RustFS S3, OpenSearch, Qdrant and dedicated Neo4j Community
providers are also implemented. No deployment format provisions an implicit
project database or `database` Secret. New consumers use approved `v1alpha2`
component bindings. Application removal and resource retirement retain data;
resource purge requires scoped confirmation and verified off-host backup intent.
See the [named-store reference](../docs/operators/data-stores.md).

## Local endpoints

After [bootstrap](../docs/operators/install-local.md):

| Endpoint | Purpose |
| --- | --- |
| `http://localhost:8000/` | React control-plane portal |
| `http://localhost:8000/docs` | Interactive API documentation |
| `http://localhost:8000/openapi.json` | Live generated OpenAPI contract |
| `http://localhost:8000/healthz` | API process health |
| `http://localhost:8000/readyz` | PostgreSQL and Kubernetes connectivity |
| `http://identity.localhost` | Keycloak reference identity provider |
| `http://localhost:3000` | Operator Grafana |
| `http://localhost:9090` | Operator Prometheus |

API and monitoring host ports bind to loopback. Caddy serves the configured
platform and identity domains; public deployments use HTTPS. Protected
`v1alpha2` application traffic follows Caddy → k3d/Traefik → hosted-access
boundary → application Service. Separate store console routes expose only
authorized human leases. Local `.localhost` HTTP routes are development paths.

<a id="access-validation-portal"></a>
<a id="api-reference"></a>

## Identity and API contracts

Humans use the `platform-portal` Authorization Code + PKCE client or
`platform-cli` Device Authorization + PKCE client. Before the first API start,
set `PLATFORM_BOOTSTRAP_SUBJECT` to the first human administrator's immutable
Keycloak subject. After the one-time grant is persisted, remove the setting.
The API validates issuer, signature, audience and lifetime, then checks current
platform-owned grants. A platform or project role grants no hosted-application
membership and no direct store data access.

Project deployment credentials authorize CI deployments and inspection within
their scope. Hosted service-access credentials authorize application routes.
Human store grants authorize expiring native credentials. These are separate
credential lifecycles. Follow the [identity guide](../docs/operators/identity-and-access.md)
and [API guide](../docs/developers/api.md).

The preferred deployment body is `platform.example/v1alpha2`. Earlier
`v1alpha1` and flat forms remain accepted for unbound applications; their public
routes retain legacy behavior. The [declaration reference](../docs/developers/application-spec.md)
covers component counts, probes, resources, bindings, telemetry and egress.
The [committed OpenAPI schema](../docs/api/openapi.json) lists all public operations.

Accepted deployments return `202` with an operation ID, revision and status URL.
The durable worker rechecks authority and revision freshness before applying
resources. `succeeded` describes apply completion; live readiness is separate.
Use `If-Match` to avoid overwriting concurrent revisions. Rollback reuses a
retained declaration as a new revision and does not restore data, migrations or
historical secret values. Hosted-access ETags and store body versions have
separate concurrency contracts.

## Runtime boundaries

Workloads run as UID/GID 10001, with a read-only root filesystem, dropped
capabilities, RuntimeDefault seccomp and writable ephemeral `/tmp` (64 MiB).
Ordinary pods receive no Kubernetes ServiceAccount token. Tracing opt-in projects
a short-lived Pod-bound token for the telemetry audience only.

Private components communicate within their namespace. Protected public backends
accept authorizer traffic; sibling components use approved HTTPS service access
for the public route. Store egress is scoped to bound components and lease ports.
External CIDR/DNS TCP destinations require declaration and operator approval;
DNS addresses are pinned at apply time. Persistent volume declarations and private
image-registry credentials are unsupported.

Project configuration is revisioned; application secrets are write-only API
resources in Kubernetes and can reach every component in a project. Store Secrets
are scoped to the bound component. Private PostgreSQL/Bolt transport is plaintext
inside the restricted relay boundary; remote native access uses SSH. This is a
single-host trusted-workload lab without high availability or hostile-tenant
isolation.

## Observation and AI

The API exposes authorized readiness, component status, inventory, usage, drift,
bounded pod/retained logs, HTTP metrics and project-filtered traces. Missing or
failed observations are explicit states. Drift is reported rather than silently
repaired. Alloy centralizes minimized workload envelopes; free-text application
logs remain kubelet best effort. Prometheus/Loki retention is configured for
seven days (Prometheus also has a 4 GB cap); Tempo defaults to 24 hours.
Operator dashboards are provisioned from source.

AI assistance uses minimized project evidence for explanations, incident
investigation and curated development guidance. Runs require an eligible human
identity, Public/Internal classification and configured model-processing
eligibility. The implemented write path is a reviewed rollback proposal with
an exact diff hash, a human approval expiring after 15 minutes, and fresh
authorization/revision checks. The [AI operations reference](../infrastructure/monitoring/AI.md)
records configuration and evidence limits.

Audit writes use a restricted append function; ordinary API audit exports require
platform administration and use a separate reader role. Records are append-only
with no automatic pruning. Host/root and PostgreSQL superusers remain trusted
administrators. See [security and authorization](../docs/architecture/security-and-authorization.md).

<a id="configuration"></a>

## Source ownership

| Source | Responsibility |
| --- | --- |
| `app/src/app/main.py` | Core HTTP endpoints, identity bootstrap and worker lifecycle |
| `app/src/app/spec.py`, `manifests.py`, `operations.py` | Declaration validation, Kubernetes resources and durable deployment execution |
| `app/src/app/access_*.py` | Hosted policy, identity projection, authorizer and access reconciliation |
| `app/src/app/stores/` | Named providers, grants, leases, private relay, consoles, monitoring and recovery |
| `app/src/app/ai_*.py` | AI evidence, bounded model calls, durable runs and approved proposals |
| `app/src/app/telemetry_*.py`, `tracing.py`, `trace_read.py` | Authenticated telemetry collection and bounded reads |
| `cli/`, `ui/` | Public API clients and their tests |
| `compose.yaml`, `../scripts/up.sh` | Runtime wiring and cluster bootstrap |

`app/pyproject.toml` and `app/uv.lock` define API dependencies (Python 3.12+);
`Dockerfile` pins the container runtime. `../.env.example` is the documented
operator input; `scripts/init.py` creates missing keys while preserving existing
values. Choose network addresses before first startup. Domain/IP changes require
review and application reapply; changing `K3S_IMAGE` does not migrate a cluster.

## Develop and validate

From the repository root:

```bash
uv sync --project platform/app --locked
uv run --project platform/app python -m unittest discover -s platform/app/tests -v
uv run --project platform/app python scripts/generate/export_openapi.py --check
python3 scripts/generate/generate-cli-contract.py --check
python3 scripts/checks/check-doc-links.py
uv run --project platform/app python -m compileall -q platform/app/src/app scripts
bash -n scripts/up.sh scripts/down.sh
docker compose config --quiet
```

Some tests require explicitly configured disposable dependencies and otherwise
skip. See [test boundaries](../docs/maintainers/testing-requirements.md),
the [CLI README](cli/README.md), [UI README](ui/README.md) and CI workflows.

Rebuild through `bash scripts/up.sh` only when updating the intended lab.
Live smoke creates or updates a retained project; follow
[acceptance](../docs/operators/validation/acceptance.md) and record the revision,
scope and cleanup outcome. Named PostgreSQL isolation and data-preservation
drills have source-level checks but still need live runs; see the
[current review disposition](../docs/maintainers/documentation-review.md#current-disposition-october-19-2026).
The backlog distinguishes source tests from deployed
acceptance; a local pass does not close outstanding operational criteria.
