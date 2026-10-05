# Docker-based Developer Platform Lab

A developer platform lab running on an existing Ubuntu host, with Docker Compose
for shared services and k3d/k3s for application workloads. No additional cloud
server or KVM virtual machines are required.

```text
Internet → Caddy (TLS)
              ├─ Platform API (Docker)
              └─ k3d LoadBalancer → Traefik → project-* namespaces
                                              └─ PostgreSQL (Docker)
Docker: Prometheus, Grafana, Loki, Alloy, Alertmanager, node-exporter
External web hosting: PHP/MySQL watchdog ← systemd heartbeat from the host
```

## Features

- Compose modules for the proxy, persistence, monitoring, and control plane.
- k3d with one server and two agents; the API listens only on loopback, with
  persistent PostgreSQL data stored outside the cluster.
- OIDC-authenticated platform API with individual principals, platform-owned
  project grants, revocation, and redacted audit events. Each project gets a database and login, Secret,
  Namespace, Deployment, Service, Ingress, Quota, LimitRange, and NetworkPolicy.
- Unprivileged workloads without Kubernetes API tokens, with read-only root
  filesystems and restricted network access.
- Persistent project state; repeating a PUT repairs partial failures without deleting data.
- Monitoring, Docker log collection, SQL backups, and an independent watchdog.
- Catalog-driven application probes with shared alerts and explicit retirement; see
  [application availability monitoring](infrastructure/monitoring/README.md).

This is a working foundation for administration and lab use on a single host.
A full self-service portal and automated deletion workflows are not yet
implemented. The Python worker executes durable deployment operations and
reclaims interrupted operations after restart. The API and its Kubernetes
ServiceAccount remain privileged infrastructure components.

See the [platform guide](platform/README.md) for API usage, project lifecycle,
application requirements, configuration, and troubleshooting.

## Quick start on Ubuntu / WSL2

Requirements: Docker Engine with Compose >= 2.20.3, Python >= 3.10, Bash,
kubectl 1.36.x (1.35.x–1.37.x are supported), and internet access. Suggested capacity:
16 vCPUs and 32 GB RAM. Docker requires access to Linux cgroups and privileged
k3d containers.

```bash
python3 scripts/init.py
python3 scripts/install-k3d.py
# Create the initial Keycloak user and set its immutable ID as PLATFORM_BOOTSTRAP_SUBJECT in .env.
docker compose up -d postgres keycloak-db-init keycloak proxy
bash scripts/up.sh
python3 scripts/smoke.py
```

`init.py` generates random secrets in a private `.env` file excluded from version
control. It does not overwrite existing values. k3d is installed locally
within the project with checksum verification. Bootstrap leaves the default
kubectl context unchanged; the admin kubeconfig is in `.runtime/admin.kubeconfig`.

Sign in to [identity.localhost](http://identity.localhost) as Keycloak `admin`
with `KEYCLOAK_ADMIN_PASSWORD` from `.env`, create the initial individual user in
the `platform` realm, and set that user's **ID** as `PLATFORM_BOOTSTRAP_SUBJECT`.
The first API startup turns it into the one platform-admin grant; remove the setting
afterward. The reference `platform-cli` client requires PKCE or device authorization
and issues access tokens for audience `platform-api`.

Locally, the proxy binds only to 127.0.0.1. The API is available at
[localhost:8000/docs](http://localhost:8000/docs); Grafana is available at
[localhost:3000](http://localhost:3000) (username `admin`, password from `.env`).
The smoke test project is available at
[smoke.apps.localhost](http://smoke.apps.localhost).
If wildcard localhost resolution is unavailable, use
`curl -H 'Host: smoke.apps.localhost' http://127.0.0.1/`.

The smoke test intentionally creates the `smoke` project and retains it for
further testing. An API result of `applied` confirms that resources were applied,
not that the application is ready; the smoke test also checks the rollout.

## Create a project

```bash
# Export a short-lived OIDC access token obtained through the configured Keycloak realm.
# It is deliberately not stored in .env.
export PLATFORM_ACCESS_TOKEN='…'
curl --fail-with-body -X PUT http://127.0.0.1:8000/projects/hello \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @examples/project.json
```

The example uses `hashicorp/http-echo` on port 5678.
Custom images must run as UID/GID 10001, without write access to the root filesystem,
and on a port >=1024. `/tmp` is writable. PostgreSQL connection details are injected
as `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`.

Network access is restricted to the same namespace, DNS, and PostgreSQL.
Ingress is allowed only through Traefik. External APIs require explicit additional
NetworkPolicies. NetworkPolicy does not provide strong isolation against a
compromised host/node; all components share the same Docker host.

## Deploy to the existing Hetzner host

For automated host setup and deployment, use the [Ansible playbook](ansible/README.md).
The manual procedure is below.

1. Copy the repository to `/opt/developer-platform` and install the prerequisites.
2. Run `python3 scripts/init.py`, then configure `.env`:
   `PLATFORM_DOMAIN=platform.example.com`, `APPS_DOMAIN=apps.example.com`, and
   `IDENTITY_DOMAIN=identity.example.com`,
   a valid `TLS_EMAIL`, and `EDGE_BIND_IP=0.0.0.0`.
3. Point DNS for the platform, identity service, and `*.apps.example.com` to the host IP.
   Allow public access only to SSH from the admin network and TCP ports 80/443;
   UDP port 443 is optional for HTTP/3. Account for Docker port publishing in
   the firewall configuration.
4. Check subnet `172.30.80.0/24` and the fixed PostgreSQL IP for conflicts.
   Make any changes before the first deployment.
5. Run `python3 scripts/install-k3d.py` and `bash scripts/up.sh`.
6. Access Grafana/Prometheus through an SSH tunnel, for example:
   `ssh -L 3000:127.0.0.1:3000 user@host`.
7. Set up the watchdog and backups using the operations guides linked below.

Caddy obtains TLS certificates for the platform automatically. For workloads,
the on-demand TLS endpoint authorizes certificates only for provisioned project
hosts; wildcard DNS does not require a wildcard certificate here.
Production TLS has not been tested locally with real DNS names and ACME.

## Operations

Current procedures: [deployment and lifecycle](docs/05-operations/deployment.md),
[incident runbook](docs/05-operations/runbook.md), and
[monitoring checks](docs/05-operations/monitoring.md).

- Status: `docker compose ps`; cluster:
  `kubectl --kubeconfig .runtime/admin.kubeconfig get pods -A`.
- Stop without losing data: `docker compose stop` and
  `.runtime/bin/k3d cluster stop workloads`.
- Restart: `bash scripts/up.sh`.
- Tear down containers and the Kubernetes cluster: `bash scripts/down.sh`.
  Persistent service data is retained; after bootstrap, reapply saved project specs
  as described in [recovery](docs/05-operations/backup-recovery.md).
- Tear down and delete all lab service data: `bash scripts/down.sh --volumes`.
  Both modes preserve `.env`, local backups, and installed tools.
- Never delete Compose volumes or k3d resources if their data is still needed.
- Store `.env`, especially `DATABASE_KEY`, securely with encryption.
  It is used to derive stable project passwords. Changing it requires coordinated
  rotation of database roles and Kubernetes Secrets.
- The external controller uses a long-lived, restricted ServiceAccount token.
  To rotate it, delete the `provisioner-token` Secret, rerun `up.sh`,
  and run `docker compose restart platform-api`.
- Make version changes explicitly and test them. Bootstrap does not automatically
  migrate an existing k3d cluster to a new image version.
- After partial SQL/Kubernetes failures, the status remains `failed`; repeat the
  same PUT request. Databases are never deleted automatically.

[Backup and recovery](docs/05-operations/backup-recovery.md) ·
[Operational tooling](operations/README.md) ·
[Watchdog installation](operations/watchdog/README.md) ·
[Architecture decisions](docs/03-decisions/README.md)

## Validation

```bash
docker compose config --quiet
python3 -m pip install -r platform/requirements-dev.txt
python3 -m unittest discover -s platform/tests -v
python3 scripts/check-monitoring.py
python3 -m unittest discover -s operations/backup/tests -v
python3 -m compileall -q platform scripts operations
bash -n scripts/up.sh scripts/down.sh
python3 scripts/smoke.py
```

Additional live checks:
`python3 scripts/isolation.py` tests PostgreSQL and network isolation after
policies have converged; it retains the `isolation` test project.
`python3 operations/watchdog/scripts/test-watchdog.py` starts temporary PHP/MariaDB containers and
removes only that test project afterward. Email handoff is simulated;
no emails are sent.

**Observed limitation:** New pods may briefly have outbound network access before
kube-router rules take effect. This installation is intended for trusted lab
workloads, not untrusted multi-tenancy.

With PHP >=8.2, PDO-MySQL, and optionally cURL, run:
`php operations/watchdog/tests/watchdog.php` and `php -l` for all PHP files.
CI runs syntax/configuration checks and unit tests; the full integration test
requires a Docker host with k3d.

## Technical references

- [k3d configuration](https://k3d.io/stable/usage/configfile/)
- [Compose modules](https://docs.docker.com/reference/compose-file/include/)
- [Kubernetes NetworkPolicies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Caddy On-Demand TLS](https://caddyserver.com/docs/automatic-https#on-demand-tls)
