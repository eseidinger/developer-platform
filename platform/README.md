# Docker-based Developer Platform Lab: platform guide

The platform API provisions applications on the lab's Kubernetes cluster and
creates a PostgreSQL database for each project. The current interface includes a
small browser portal plus a REST API with interactive documentation. Both enforce
individual OIDC identities and platform-owned project grants.

For installation and prerequisites, start with the [main README](../README.md).
See [architecture](../docs/02-architecture/infrastructure.md) for isolation and availability limits,
and [backup and recovery](../docs/05-operations/backup-recovery.md) for operational procedures.

## Access the platform

After `bash scripts/up.sh` completes, these local endpoints are available:

| Endpoint | Purpose |
| --- | --- |
| `http://localhost:8000/` | Keycloak login and human access-validation portal |
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

For the full local bootstrap, Device Authorization with PKCE, scoped-role, and
revocation evidence procedure, see the [human access and authorization validation runbook](../docs/05-operations/human-access-and-authorization-validation.md).

## Access-validation portal

Open the platform root URL after Keycloak bootstrap completes. The portal uses
the `platform-portal` public Keycloak client with Authorization Code + PKCE; it
keeps the access token only in browser memory and never displays it. On each
deployment, `keycloak-realm-init` reconciles the client to the configured exact
`PLATFORM_DOMAIN` redirect URI and web origin.

The portal can create/reapply disposable projects, grant or revoke project and
platform roles, list accessible projects, and call the restricted
operator-inspection and redacted audit-export endpoints. Create distinct test
users in Keycloak first, then sign in separately as each user to record the
viewer/developer/project-admin denial matrix. It does not administer Keycloak
users or store test subjects, evidence, or credentials.

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
  "operation_id": "69fb09ef-5136-4c8a-8ec1-c57467192b9a",
  "state": "queued",
  "revision": 1,
  "status_url": "/v1/operations/69fb09ef-5136-4c8a-8ec1-c57467192b9a"
}
```

The API returns `202 Accepted` after atomically persisting the desired revision
and operation. The in-process worker applies the resources and the operation
status reports `succeeded` or a sanitized failure code. The separate live
`readiness` snapshot reports desired/ready replicas, the desired and applied
Deployment images, images and image IDs running in ready pods, and a diagnostic reason.
Readiness does not change the operation's apply outcome:

```bash
OPERATION_ID=69fb09ef-5136-4c8a-8ec1-c57467192b9a
curl --fail-with-body "http://127.0.0.1:8000/v1/operations/$OPERATION_ID" \
  -H "Authorization: ******"
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

The operation response keeps the apply outcome separate from live observation.
For example:

```json
{
  "state": "succeeded",
  "readiness": {
    "state": "progressing",
    "desired_replicas": 1,
    "ready_replicas": 0,
    "desired_image": "hashicorp/http-echo:1.0.0",
    "deployment_image": "hashicorp/http-echo:1.0.0",
    "active_images": [],
    "active_image_ids": [],
    "reason": "ImagePullBackOff",
    "observed_at": "2026-10-03T12:00:00+00:00"
  }
}
```

You can also open [hello.apps.localhost](http://hello.apps.localhost) if the local
resolver supports wildcard localhost names. Public applications use
`https://<name>.<APPS_DOMAIN>` after DNS and TLS are configured.

## Project specification

`PUT /projects/{name}` accepts a versioned envelope (the preferred format for new integrations) or the flat body below, which remains supported without a sunset date and maps to the same revisions. The envelope has (`apiVersion: platform.example/v1alpha1`, `kind: Application`; see [ApplicationSpec](../docs/02-architecture/application-spec.md)). The generated API contract is [docs/api/openapi.json](../docs/api/openapi.json); refresh it with `scripts/export_openapi.py` after API changes (a test fails when it is stale).

| Field | Required | Contract |
| --- | --- | --- |
| `name` | Yes | 1–32 lowercase letters, digits, or hyphens; start with a letter and end with a letter or digit. Must match the URL path. |
| `image` | Yes | Container image reference, 2–512 characters under the current regex. An explicit tag or digest is recommended but not enforced. |
| `port` | No | Container TCP port, 1024–65535; defaults to 8080. |
| `probe_profile` | No | `status` (default) or `hello-world`; root-path availability/content check. |
| `resources` | No | `{"requests": {"cpu", "memory"}, "limits": {"cpu", "memory"}}`; CPU as `250m` or `0.25`, memory as `Mi`/`Gi`. Omitted values default to requests `100m`/`128Mi` and limits `500m`/`256Mi`. Requests must not exceed limits; maxima are requests 1 CPU/1Gi and limits 2 CPU/2Gi (a rolling update briefly runs two pods within the namespace quota). Invalid values return 422. Spec rejections return 422 with a stable `code`: `unsupported_capability` (a field or value outside the declared capabilities) or `invalid_spec` (anything else malformed). Stored canonically (`250m`, `512Mi`), so equivalent spellings reuse the revision. |

Unknown project request fields are rejected with `422` before catalog or provider side effects. Tags and untagged image references are accepted without digest resolution. Use an immutable digest when reproducibility matters. The [v1alpha1 ApplicationSpec](../docs/02-architecture/application-spec.md) is a future contract, not an input format for this endpoint.

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
image or port. PUT accepts an optional `If-Match: <revision>` header (`0` for a new project); when it differs from the current desired revision the request returns 409 with `code: revision_conflict` and `current_revision`, with no side effects, and without the header the last writer wins. Each new revision prunes older ones beyond `REVISION_RETENTION` (default 25); the current revision, revisions with queued or running operations and the last successful restart (which also keeps the revision it ran at) are kept, and the pruned revisions' finished operations (and their status URLs) are removed with them. PUT is idempotent: repeating the same request reapplies the desired
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
| `provisioning` | A desired revision is queued or being applied. A worker restart reclaims interrupted operations. | Follow its operation ID; retry the same request after resolving a failure. |
| `applied` | The request completed resource application. | Check rollout and application behavior. |
| `failed` | Provisioning encountered an error and recorded the failure. | Resolve the cause and repeat the same PUT. |
| `retired` | Administrator acknowledged namespace removal; monitoring ended and SQL data/spec remain. | PUT explicitly reactivates the application. |

Revision and operation acceptance are serialized with a PostgreSQL advisory lock
and committed together. The in-process worker executes provider changes outside
that transaction under an operation lock and the shared lifecycle lock. Retrying
an interrupted operation starts again from idempotent ensure steps. The separate
monitoring-only loop republishes application probe targets but does not reconcile
workloads.

Retirement is a two-step, confirmed action. `GET /projects/{name}/retirement-preview` lists what would be removed (the project namespace and the objects in it, and the public route), what is kept (database, role, catalog and revisions), any blockers, and a `scope_token`. `POST /projects/{name}/retire` with `{"confirm_name":"<name>","scope_token":"<token>"}` then deletes the namespace, records retirement, persists the retained inventory and removes monitoring while retaining SQL data and the catalog. A new revision invalidates the token (409 `scope_changed`). While the namespace is still terminating the call answers 202 `retiring`; repeat the same request. Without `scope_token` the request keeps its earlier meaning: it only records retirement after you removed the namespace manually. Retirement is rejected while a deployment operation is queued or running. See [application monitoring and retirement](../infrastructure/monitoring/README.md). For a complete lab reset, use
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
| `GET /projects/{name}/drift` | `view` grant | Compares the live Deployment (image, replicas, CPU/memory) with the desired revision and returns `in_sync`, `drifted` with per-field differences, `not_found` or `unknown`. Report only: it never changes the cluster; drift is audited as `project.drift.detected`; a background scan (every `DRIFT_SCAN_INTERVAL_SECONDS`, default 300) audits only changes for applied projects, as `project.drift.detected` and `project.drift.resolved` by actor `system`/`drift-scan`. Re-apply with PUT or restart |
| `GET /v1/capabilities` | Any authenticated principal | Declared capabilities per environment (runtime, endpoints, scaling, resources, health, external resources, configuration; `secrets: true` means secrets exist through the secrets endpoints, never inside the spec) and the allowed image registries |
| `PUT /projects/{name}` | OIDC `developer` or stronger project grant; platform-admin creates projects | 202 with queued operation ID, desired revision, and status URL; the image tag is first resolved to a digest (422 unknown tag/unsupported registry, 503 registry unreachable) |
| `GET /v1/operations/{id}` | OIDC `viewer` or stronger grant on the owning project | 200 with apply outcome, revision, redacted result, and live readiness snapshot (replica counts, images, diagnostic reason) |
| `GET /projects/{name}/revisions` | `view` grant | Lists the retained revisions, newest first, with creation time, resolved image, port and resources; marks the current one |
| `GET /projects/{name}/resource-usage` | `view` grant | Current CPU (millicores) and memory (bytes) per pod and in total from the Kubernetes metrics API; `state` is `ok`, `stale` (samples older than 120 s), `missing` (no samples) or `unavailable` (metrics API not queryable), never a silent zero |
| `GET /projects/{name}/logs` | `view` grant | Recent timestamped log lines with pod/container attribution, merged by time. `tail` (1-1000), `since_seconds`, `component`, exact pod `instance`, case-insensitive `search`, and lexical RFC3339 `after`/`before` bound the read. Repeat with returned `next_cursor` as `after` to poll for new lines. Terminal pods remain readable while their kubelet logs remain available; `retention` reports that best-effort boundary. Credentials are redacted on a best-effort basis and lines are capped at 2000 characters. |
| `GET /projects/{name}/configuration` | `view` grant | Current desired configuration values, the revision, and `activation` (`active`, `rolling_out`, `pending` until the Deployment carries the values, or `unknown`). Values are visible to every viewer, so secrets must not be stored here
| `PUT /projects/{name}/configuration` | `change` grant | Body `{"values": {NAME: "value"}}` replaces the set (add, update, remove). Validated first: names are env-var names, not `PG*`, `KUBERNETES_*`, `PLATFORM_*` or secret-like (`PASSWORD`, `TOKEN`, ...), at most 50 values of 1024 characters; otherwise 422 `invalid_configuration`. Creates a new revision (optional `If-Match`) and rolls the pods; the 202 reports `rollout_required`. Also accepted as `spec.configuration.values` in the envelope or `configuration` in the flat body. Audit records names, never values |
| `GET /projects/{name}/secrets` | `view` grant | Secret names, versions, states and change times only, never values, plus `activation` (`active`, `rolling_out`, `pending`, `unknown`) for whether the pods run the current version
| `PUT /projects/{name}/secrets/{NAME}` | `change` grant | Body `{"value": "..."}` creates or rotates one write-only secret (name rules as configuration but secret-like names are allowed; at most 50 secrets, 8192 characters each; 422 `invalid_secret`, 409 `name_in_use` if the name is a configuration value). The value lives only in the project's `app-secrets` Kubernetes Secret, is injected as an environment variable, and is never stored in revisions or audit records. Pods restart to pick it up (`rollout_required`). Rotating keeps the replaced value in the unmounted `app-secrets-previous` Secret (listing shows `version` and `state` `rotating`) until `confirm` or the next `revert`. Retiring a project deletes the Secret with the namespace |
| `POST /projects/{name}/secrets/{NAME}/confirm` | `change` grant | Revokes the previous value once the pods run the new version; 409 `not_adopted` before that, 409 `no_previous_version` when none is held |
| `POST /projects/{name}/secrets/{NAME}/revert` | `change` grant | Makes the previous value current again as a new version and restarts the pods; 409 `no_previous_version` when none is held |
| `DELETE /projects/{name}/secrets/{NAME}` | `change` grant | Removes one secret and restarts the pods; 404 if it does not exist |
| `POST /projects/{name}/rollback` | `change` grant | Body `{"revision": N}`. Re-applies retained revision N's stored spec (including its image digest) as a new revision and queues a normal deploy, so history stays append-only; 202 as for PUT; optional `If-Match`; 404 unknown or pruned revision; 409 retired project. Only the application changes: database contents and roles are never rolled back or migrated |
| `POST /projects/{name}/restart` | OIDC `developer` or stronger project grant | 202 with a queued `restart` operation that rolls the current deployed revision without changing the spec; repeats reuse the pending operation; 404 unknown, 409 unless applied |
| `GET /projects/{name}/retirement-preview` | OIDC `project-admin` or `platform-admin` | Objects removed, data retained, blockers and `scope_token` |
| `POST /projects/{name}/retire` | OIDC `project-admin` or `platform-admin`, plus matching `confirm_name` and optional `scope_token` | With a token: deletes the namespace; 200 retired, 202 `retiring` while it terminates, 409 `scope_changed` for a stale token. Without a token: 200 after manual removal, 409 while the namespace exists. 409 while an operation is active; data is always retained |
| `PUT` / `DELETE /projects/{name}/grants` | OIDC `project-admin` or `platform-admin` for that project | Create, change, or revoke a project grant |
| `PUT` / `DELETE /platform/grants` | OIDC `platform-admin` | Create or revoke another platform-admin grant |
| `GET /internal/tls?domain=...` | None; used by Caddy | 200 for a project host whose stored status is `applied`; 403 for an unauthorized host |

The TLS authorization route is excluded from OpenAPI and does not provision projects.
A missing or invalid bearer token is rejected. PUT returns 400 if the URL and body
names differ, 422 for invalid request fields, and 503 when operation acceptance or
its required audit record fails.

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
Project database roles cannot connect to the `platform` database. Only a
`platform-admin` may call the `/operator/*` inspection endpoints: project-grant
inspection, managed workload/network-security configuration inspection, and a
bounded time-filtered audit export. The API reads exports through the separate
reader login and redacts again before returning JSON or CSV. Project members,
including project administrators, cannot access these endpoints.

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
| PUT returns 503 | Inspect `docker compose logs --tail=100 platform-api`, PostgreSQL, and audit availability. Resolve the acceptance failure and retry the same PUT. |
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
python3 -m unittest discover -s platform/tests -v
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
