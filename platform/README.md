# Docker-based Developer Platform Lab: platform guide

The platform API provisions applications on the lab's Kubernetes cluster and
creates a PostgreSQL database for each project. It is intended for trusted
administrators. The current interface is a REST API with interactive documentation;
there is no self-service portal or tenant-specific authorization.

For installation and prerequisites, start with the [main README](../README.md).
See [architecture](../docs/architecture.md) for isolation and availability limits,
and [backup and recovery](../docs/operations.md) for operational procedures.

## Access the platform

After `bash scripts/up.sh` completes, these local endpoints are available:

| Endpoint | Purpose |
| --- | --- |
| `http://localhost:8000/docs` | Interactive API documentation |
| `http://localhost:8000/openapi.json` | OpenAPI schema |
| `http://localhost:8000/healthz` | API process health |
| `http://localhost:8000/readyz` | Database and Kubernetes connectivity |
| `http://localhost:3000` | Grafana; username `admin`, password from `.env` |
| `http://localhost:9090` | Prometheus |

The API and monitoring host ports bind to loopback. For a public deployment, Caddy
routes the configured `PLATFORM_DOMAIN` to the API over HTTPS. Application requests
follow Caddy → k3d load balancer → Traefik → project Service → application pod.

Project endpoints require the `PLATFORM_TOKEN` from `.env` as a bearer token.
In the interactive documentation, use **Authorize** to supply the token.
The token grants administrative access to all projects; do not distribute it to
application users. The API does not return database passwords in project responses.

## Create an application

Run commands from the repository root. Load the local settings into a trusted shell:

```bash
eval "$(python3 scripts/env.py)"
```

Create the example application:

```bash
curl --fail-with-body -X PUT http://127.0.0.1:8000/projects/hello \
  -H "Authorization: Bearer $PLATFORM_TOKEN" \
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
| `image` | Yes | Container image reference, 1–512 characters. Use an explicit tag or digest. |
| `port` | No | Container TCP port, 1024–65535; defaults to 8080. |

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
  -H "Authorization: Bearer $PLATFORM_TOKEN"
```

Each list entry contains `name`, `spec`, and `status`, ordered by project name.
The stored status describes provisioning rather than ongoing application health:

| Status | Meaning | Next step |
| --- | --- | --- |
| `provisioning` | A request is applying resources, or the process stopped during provisioning. | If it remains stuck, inspect the API and repeat the PUT. |
| `applied` | The request completed resource application. | Check rollout and application behavior. |
| `failed` | Provisioning encountered an error and recorded the failure. | Resolve the cause and repeat the same PUT. |

Provisioning runs synchronously and is serialized with a PostgreSQL advisory lock.
Database and Kubernetes operations do not form a single transaction. Partial failures
can leave resources in place, and early failures may prevent a status from being
recorded. There is no background reconciler; repeat PUT to repair the desired state.

There is no project deletion endpoint. For a complete lab reset, use
`bash scripts/down.sh --volumes`, then bootstrap again. Running `down.sh` without
`--volumes` retains the stored project catalog and databases, but removes Kubernetes
workloads. Reapply the saved specifications after bootstrap as described in
[recovery](../docs/operations.md).

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
| `GET /projects` | Admin bearer token | 200 with the stored project list |
| `PUT /projects/{name}` | Admin bearer token | 200 with the applied project name, namespace, and host |
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
| `PLATFORM_TOKEN` | Admin API token; at least 32 characters |
| `DATABASE_KEY` | Master secret for deterministic project passwords; at least 32 characters |
| `POSTGRES_PASSWORD` | PostgreSQL administrator password |
| `GRAFANA_PASSWORD` | Initial Grafana admin password |
| `PLATFORM_SUBNET` | Private Docker subnet; default `172.30.80.0/24` |
| `POSTGRES_IP` | Fixed PostgreSQL address within that subnet; default `172.30.80.10` |
| `K3S_IMAGE` | Cluster image; currently `rancher/k3s:v1.36.4-k3s1` |

Choose network settings before startup. Updating a domain or IP does not rewrite
previously provisioned project resources until they are reapplied. Updating
`K3S_IMAGE` does not replace an existing cluster. See the
[recreation instructions](../docs/operations.md) when changing lab versions.

The API's internal `POSTGRES_HOST` and `KUBECONFIG` settings are supplied by
[its Compose module](compose.yaml). Bootstrap generates the controller kubeconfig
in `.runtime/controller.kubeconfig` and mounts it read-only into the API container.

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
provisioning, and Kubernetes reconciliation. [app/manifests.py](app/manifests.py)
defines the workload resources and can be tested without a live cluster.
[requirements.txt](requirements.txt) pins direct Python dependencies, while
[Dockerfile](Dockerfile) defines the Python 3.14.7 API runtime.

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q platform scripts
bash -n scripts/up.sh scripts/down.sh scripts/backup.sh
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
