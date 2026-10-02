# Docker-based Developer Platform Lab: platform guide

The platform API provisions applications on the lab's Kubernetes cluster and
creates a PostgreSQL database for each project. The current interface is a REST API
with interactive documentation; it has no portal, but it does enforce individual
OIDC identities and platform-owned project grants.

For installation and prerequisites, start with the [main README](../README.md).
See [architecture](../docs/02-architecture/infrastructure.md) for isolation and availability limits,
and [backup and recovery](../docs/05-operations/backup-recovery.md) for operational procedures.

## Access the platform

After `bash scripts/up.sh` completes, these local endpoints are available:

| Endpoint | Purpose |
| --- | --- |
| `http://localhost:8000/docs` | Interactive API documentation |
| `http://localhost:8000/openapi.json` | OpenAPI schema |
| `http://localhost:8000/healthz` | API process health |
| `http://localhost:8000/readyz` | Database and Kubernetes connectivity |
| `http://identity.localhost` | Keycloak reference identity service |
| `http://localhost:3000` | Grafana; username `admin`, password from `.env` |
| `http://localhost:9090` | Prometheus |

The API and monitoring host ports bind to loopback. For a public deployment, Caddy
routes the configured `PLATFORM_DOMAIN` to the API over HTTPS. Application requests
follow Caddy → k3d load balancer → Traefik → project Service → application pod.

Project endpoints require a short-lived OIDC access token. In the interactive
documentation, use **Authorize** to supply that token. The API validates its issuer,
signature, audience and lifetime, then uses the issuer/subject pair to look up a
platform-owned grant. It does not accept the old shared administrator token and does
not return database passwords in project responses.

The reference Keycloak realm is `platform` and its public client is `platform-cli`.
Create individual users in Keycloak; never create a shared developer account. Before
the first API start, set `PLATFORM_BOOTSTRAP_SUBJECT` to the immutable Keycloak user
ID (`sub`) for the first platform administrator. The API writes this one-time grant
to PostgreSQL and will not recreate it on later starts. Remove the bootstrap setting
after recording the controlled setup evidence.

## Create an application

Run commands from the repository root. Export a short-lived access token from the
configured OIDC client; do not put it in `.env`:

```bash
export PLATFORM_ACCESS_TOKEN='…'
```

Create the example application:

```bash
curl --fail-with-body -X PUT http://127.0.0.1:8000/projects/hello \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @examples/project.json
```

The [example specification](../examples/project.json) is:

```json
{
  "name": "hello",
  "image": "hashicorp/http-echo:1.0.0",
  "port": 5678
}
```

With the default application domain, a successful response is:

```json
{
  "name": "hello",
  "status": "applied",
  "namespace": "project-hello",
  "host": "hello.apps.localhost"
}
```

`applied` means Kubernetes accepted the resources. Check the rollout separately:

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig \
  -n project-hello rollout status deployment/hello --timeout=180s
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

You can also open [hello.apps.localhost](http://hello.apps.localhost) if the local
resolver supports wildcard localhost names. Public applications use
`https://<name>.<APPS_DOMAIN>` after DNS and TLS are configured.

## Project specification

| Field | Required | Contract |
| --- | --- | --- |
| `name` | Yes | 1–32 lowercase letters, digits, or hyphens; start with a letter and end with a letter or digit. Must match the URL path. |
| `image` | Yes | Container image reference, 2–512 characters under the current regex. An explicit tag or digest is recommended but not enforced. |
| `port` | No | Container TCP port, 1024–65535; defaults to 8080. |
| `probe_profile` | No | `status` (default) or `hello-world`; root-path availability/content check. |

Unknown fields are silently ignored by the current Pydantic model; they are not applied or rejected. Tags and untagged image references are accepted without digest resolution. Use an immutable digest when reproducibility matters. The [v1alpha1 ApplicationSpec](../docs/02-architecture/application-spec.md) is a future contract, not an input format for this endpoint.

The API currently accepts no configuration fields for replicas, resource limits,
custom environment variables, volumes, image pull secrets, or application commands.
Use an image that the cluster can pull with its available registry configuration.
Image validation checks the reference's characters and length, not whether it exists
or whether the application can run successfully.

For project `hello`, provisioning creates:

| Resource | Name or behavior |
| --- | --- |
| PostgreSQL database and login role | `project_hello`; hyphens in project names become underscores |
| Namespace | `project-hello`, with Kubernetes 1.36 restricted Pod Security enforcement |
| Secret | `database`, containing PostgreSQL connection environment variables |
| Deployment | `hello`, with one replica |
| Service | `hello`, port 80 forwarding to the specified application port |
| Ingress | `hello`, routing `<name>.<APPS_DOMAIN>` through Traefik |
| ResourceQuota and LimitRange | `budget` and `defaults` |
| NetworkPolicy | `isolation` |

## Update and recover a project

Send another PUT to the same URL with the complete specification to update its
image or port. PUT is idempotent: repeating the same request reapplies the desired
resources without deleting the database or changing its password, provided
`DATABASE_KEY` remains unchanged.

List stored projects and their latest specifications:

```bash
curl --fail-with-body http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN"
```

Each list entry contains `name`, `spec`, and `status`, ordered by project name.
The stored status describes provisioning rather than ongoing application health:

| Status | Meaning | Next step |
| --- | --- | --- |
| `provisioning` | A request is applying resources, or the process stopped during provisioning. | If it remains stuck, inspect the API and repeat the PUT. |
| `applied` | The request completed resource application. | Check rollout and application behavior. |
| `failed` | Provisioning encountered an error and recorded the failure. | Resolve the cause and repeat the same PUT. |
| `retired` | Administrator acknowledged namespace removal; monitoring ended and SQL data/spec remain. | PUT explicitly reactivates the application. |

Provisioning runs synchronously and is serialized with a PostgreSQL advisory lock.
Database and Kubernetes operations do not form a single transaction. Partial failures
can leave resources in place, and early failures may prevent a status from being
recorded. There is no workload reconciler; repeat PUT to repair the desired state. A separate monitoring-only loop republishes application probe targets from the catalog.

There is no automated project deletion endpoint. After deliberate manual namespace removal, authenticated `POST /projects/{name}/retire` with `{"confirm_name":"<name>"}` records retirement and removes monitoring while retaining SQL data and the catalog. See [application monitoring and retirement](../infrastructure/monitoring/README.md). For a complete lab reset, use
`bash scripts/down.sh --volumes`, then bootstrap again. Running `down.sh` without
`--volumes` retains the stored project catalog and databases, but removes Kubernetes
workloads. Reapply the saved specifications after bootstrap as described in
[recovery](../docs/05-operations/backup-recovery.md).

## Automatic availability monitoring

Every project is registered for a root-path HTTP 200 check (`probe_profile: "status"`). Use `probe_profile: "hello-world"` to additionally check the smoke response body. Existing specs default to `status`; include the profile in every full-spec PUT to preserve it. Failed deployments stay monitored; only explicit retirement removes a target. Local `.localhost` installations use HTTP through Caddy; public domains use verified HTTPS from the platform host. See [configuration, limits and validation](../infrastructure/monitoring/README.md).

## Application runtime contract

Applications must listen on the configured port on all container interfaces and
run as UID/GID 10001. The root filesystem is read-only, Linux capabilities are
dropped, privilege escalation is disabled, and no Kubernetes ServiceAccount token
is mounted. `/tmp` is writable ephemeral storage with a 64 MiB size limit.
Store durable application data in PostgreSQL; persistent volume claims are disabled.

| Setting | Value |
| --- | --- |
| Replicas | 1 |
| CPU request / limit | 100m / 500m |
| Memory request / limit | 128 MiB / 256 MiB |
| Readiness probe | TCP connection to the application port every 5 seconds |
| Liveness probe | TCP connection to the application port, initial delay 30 seconds |
| Namespace CPU requests / limits | 2 / 4 cores |
| Namespace memory requests / limits | 2 GiB / 4 GiB |
| Namespace object limits | 10 pods, 5 Services, no LoadBalancer or NodePort Services, no PVCs |

TCP probes verify an open port, not application-level correctness. Namespace quotas
are upper bounds; they do not reserve host capacity.

The `database` Secret supplies `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and
`PGPASSWORD`. Each project role owns its database and has no superuser, database
creation, or role creation privileges. Passwords are derived from `DATABASE_KEY`;
changing that key requires coordinated credential rotation.

Network policy permits traffic between pods in the same namespace, DNS queries to
cluster DNS, outbound PostgreSQL connections, and inbound Traefik traffic on the
application port. Other outbound connections, including external APIs, need
additional administrator-managed policies. New pods may briefly have outbound
access before network rules converge; this lab is intended for trusted workloads.

## API reference

| Method and path | Authentication | Response |
| --- | --- | --- |
| `GET /healthz` | None | 200 with `{"status":"ok"}` when the process responds |
| `GET /readyz` | None | 200 with `{"status":"ready"}` when database and Kubernetes checks pass; otherwise 503 |
| `GET /projects` | OIDC `viewer` or stronger grant | 200 with only authorized projects |
| `PUT /projects/{name}` | OIDC `developer` or stronger project grant; platform-admin creates projects | 200 with the applied project name, namespace, and host |
| `POST /projects/{name}/retire` | OIDC `project-admin` or `platform-admin`, plus matching `confirm_name` | 200 with retained-data retirement; 409 while namespace exists |
| `PUT` / `DELETE /projects/{name}/grants` | OIDC `project-admin` or `platform-admin` for that project | Create, change, or revoke a project grant |
| `PUT` / `DELETE /platform/grants` | OIDC `platform-admin` | Create or revoke another platform-admin grant |
| `GET /internal/tls?domain=...` | None; used by Caddy | 200 for a project host whose stored status is `applied`; 403 for an unauthorized host |

The TLS authorization route is excluded from OpenAPI and does not provision projects.
A missing or invalid bearer token is rejected. PUT returns 400 if the URL and body
names differ, 422 for invalid request fields, and 503 when provisioning fails.

## Configuration

`python3 scripts/init.py` creates `.env` from the example and generates secrets.
Rerunning it preserves the existing file. Review `.env.example` after version
updates and apply relevant settings to `.env` explicitly.

| Variable | Purpose |
| --- | --- |
| `PLATFORM_DOMAIN` | Hostname Caddy routes to the API; default `platform.localhost` |
| `APPS_DOMAIN` | Application domain suffix; default `apps.localhost` |
| `TLS_EMAIL` | Contact email Caddy uses for certificate authority registration |
| `EDGE_BIND_IP` | Proxy bind address; default `127.0.0.1`, public host setting `0.0.0.0` |
| `DATABASE_KEY` | Master secret for deterministic project passwords; at least 32 characters |
| `PLATFORM_AUDIT_PASSWORD` | Password for the restricted audit-event writer; at least 32 characters |
| `PLATFORM_AUDIT_READER_PASSWORD` | Password for the restricted audit-event reader used by security metrics; at least 32 characters |
| `IDENTITY_DOMAIN` | Keycloak hostname through Caddy; default `identity.localhost` |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak bootstrap administrator password |
| `KEYCLOAK_DB_PASSWORD` | Password for Keycloak's restricted PostgreSQL role |
| `OIDC_ISSUER` | OIDC issuer; default `http://<IDENTITY_DOMAIN>/realms/platform` |
| `OIDC_AUDIENCE` | Required access-token audience; default `platform-api` |
| `OIDC_JWKS_URL` | Internal JWKS URL; default points to the Keycloak service |
| `PLATFORM_BOOTSTRAP_SUBJECT` | One-time immutable subject for the first platform-admin grant; remove after bootstrap |
| `POSTGRES_PASSWORD` | PostgreSQL administrator password |
| `GRAFANA_PASSWORD` | Initial Grafana admin password |
| `PLATFORM_SUBNET` | Private Docker subnet; default `172.30.80.0/24` |
| `POSTGRES_IP` | Fixed PostgreSQL address within that subnet; default `172.30.80.10` |
| `K3S_IMAGE` | Cluster image; currently `rancher/k3s:v1.36.4-k3s1` |

Choose network settings before startup. Updating a domain or IP does not rewrite
previously provisioned project resources until they are reapplied. Updating
`K3S_IMAGE` does not replace an existing cluster. See the
[recreation instructions](../docs/05-operations/backup-recovery.md) when changing lab versions.

The API's internal `POSTGRES_HOST` and `KUBECONFIG` settings are supplied by
[its Compose module](compose.yaml). Bootstrap generates the controller kubeconfig
in `.runtime/controller.kubeconfig` and mounts it read-only into the API container.
Keycloak uses its own PostgreSQL role and database, both included in the encrypted
platform database backup.

## Audit records and retention

At startup, the API creates `platform_audit.events` and the no-login owner plus
restricted reader and writer database roles. API event writes use only the writer login, which can call
the security-definer append function but has no table read, update, delete, truncate,
or schema privileges. The table rejects update, delete, and truncate statements.
Project database roles cannot connect to the `platform` database, and the API exposes
no audit-record endpoint in this stage. The separate reader login is used only to
derive bounded, redacted security-alert metrics. OPS-001-T02 will add restricted
operator inspection and time-filtered export.

Event details recursively redact password, secret, token, authorization, credential,
cookie, and key fields; bearer/basic credential strings are redacted as well. Store
only stable actor identifiers, target/scope, action, result, and safe failure type;
never put raw HTTP headers, access tokens, database passwords, or provider exception
text into an event.

The current retention policy is append-only with no automatic pruning: records remain
online until an owner-approved retention procedure is introduced, and the scheduled
encrypted platform backup captures the database state. This deliberately favors
investigation durability over an unverified deletion job. PostgreSQL superusers and
host/root operators remain a trusted administrative boundary and can bypass ordinary
database controls; off-host encrypted backups and restricted host access are the
current tamper-evidence and recovery safeguards. Record a controlled live check of
the append-only permissions, backup coverage, and storage growth before closing
OPS-001-T01.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Bootstrap waits for PostgreSQL | `docker compose logs --tail=100 postgres`; old major-version data needs migration or a fresh lab volume. |
| Bootstrap waits for Kubernetes | `kubectl --kubeconfig .runtime/admin.kubeconfig get nodes -o wide`; verify readiness and the actual node version. |
| API container is healthy but requests fail | Check `/readyz`; the container health check uses `/healthz`, which does not test dependencies. |
| PUT returns 503 | Inspect `docker compose logs --tail=100 platform-api`, PostgreSQL, and Kubernetes. Resolve the cause and repeat PUT. |
| Project is applied but inaccessible | Check rollout, pod events, image pulls, listening port, and ingress hostname. |
| Pod repeatedly restarts | Check logs for writes outside `/tmp`, permissions, probe failures, or memory limits. |
| Application cannot reach an external API | Check its namespace NetworkPolicies; external egress is restricted by default. |

Useful application diagnostics:

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get pods,svc,ingress
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello describe pods
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello logs deployment/hello
```

## Develop and validate

[app/main.py](app/main.py) implements request validation, authentication, database
provisioning, and request-driven Kubernetes apply. [app/manifests.py](app/manifests.py)
defines the workload resources and can be tested without a live cluster. [app/monitoring.py](app/monitoring.py) rebuilds catalog-derived probe discovery. The implemented boundaries are recorded in [ADRs 012–015](../docs/03-decisions/README.md).
[requirements.txt](requirements.txt) pins direct Python dependencies, while
[Dockerfile](Dockerfile) defines the Python 3.14.7 API runtime.

From the repository root:

```bash
python3 -m pip install -r platform/requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 -m compileall -q platform scripts
bash -n scripts/up.sh scripts/down.sh
docker compose config --quiet
```

After changing API code or dependencies, rebuild with `bash scripts/up.sh`.
Then run the live checks:

```bash
python3 scripts/smoke.py
python3 scripts/isolation.py
```

These create or update the `smoke` and `isolation` projects and retain them for
inspection. Run them only in a lab where those names are available for testing.
