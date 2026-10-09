# Developer getting started

Status: current. Last reviewed October 9, 2026.

This guide is for a developer deploying a containerized application to an existing
Developer Platform project. It covers the supported non-interactive workflow:
declare the application in JSON, keep a project-scoped deployment credential in
CI, and apply the declaration with `devplat`.

It does not cover installing or administering the platform. Ask the platform team
to create the project, grant your team access, and issue a deployment credential.
Project and credential administration are deliberately separate from application
deployment.

## Before you begin

You need the following from the platform team:

- a project name, such as `orders`;
- the Platform API URL;
- the OIDC token endpoint, deployment-credential client ID, and one-time client
  secret; and
- the public application-domain convention, if it differs from
  `https://<project>.<apps-domain>`.

The current platform profile accepts images from the configured public registries
(by default Docker Hub, GitHub Container Registry, and Quay). It does not provide
private-registry credentials or image pull secrets. Use a tagged image or,
preferably, an immutable digest.

Your container must:

- listen on its declared TCP port on all interfaces;
- run as UID/GID `10001`;
- tolerate a read-only root filesystem, dropped Linux capabilities, and no mounted
  Kubernetes service-account token; and
- use `/tmp` only for temporary data. It is writable but ephemeral and limited to
  64 MiB.

The platform supplies PostgreSQL connection settings as `PGHOST`, `PGPORT`,
`PGDATABASE`, `PGUSER`, and `PGPASSWORD`. Persistent volumes and arbitrary
outbound network access are not part of the default profile.

## Install the CLI

Install the published CLI in an isolated environment:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install developer-platform-cli
```

Open a new shell if `pipx ensurepath` changed your `PATH`, then confirm the CLI is
available:

```bash
devplat --help
```

For repository development instead, install the local package with
`python3 -m pip install -e 'platform/cli[dev]'` from the repository root.

## Declare the application

Create `application.json`. The `metadata.name` and `metadata.project` values must
match the project passed to the CLI. This example deploys one public HTTP service.

```json
{
  "apiVersion": "platform.example/v1alpha2",
  "kind": "Application",
  "metadata": {
    "name": "orders",
    "project": "orders",
    "environment": "default"
  },
  "spec": {
    "components": [
      {
        "name": "web",
        "type": "service",
        "runtime": {
          "type": "container",
          "image": "ghcr.io/acme/orders@sha256:replace-with-your-image-digest"
        },
        "ports": [
          {
            "name": "http",
            "protocol": "http",
            "port": 8080
          }
        ],
        "exposure": "public",
        "health": {
          "readiness": {
            "profile": "status"
          }
        }
      }
    ]
  }
}
```

The supported `v1alpha2` profile allows up to five components. A `service` can be
public or private; only one service may be public. Scheduled components use a
five-field UTC cron schedule and cannot expose a port. A service can have up to
five replicas, subject to project policy. Query `GET /v1/capabilities` or consult
the platform team before relying on optional capacity, egress, configuration, or
database features.

`status` readiness confirms that the configured port accepts TCP connections.
Use `hello-world` only for applications that implement the platform's smoke
response. Custom readiness paths are not supported.

## Configure authentication

Set the credential values in your terminal or CI environment. Do not put a client
secret, bearer token, or database password in `application.json`, a command-line
argument, repository file, or build log.

```bash
export PLATFORM_API_URL='https://platform.example'
export PLATFORM_TOKEN_ENDPOINT='https://identity.example/realms/platform/protocol/openid-connect/token'
export PLATFORM_CLIENT_ID='provided-by-platform-team'
export PLATFORM_CLIENT_SECRET='store-only-in-your-secret-manager'
```

The CLI exchanges this credential for a short-lived access token in memory. If you
already have a short-lived access token, set `PLATFORM_ACCESS_TOKEN` instead of the
three deployment-credential variables. The access-token variable takes precedence
when both forms are present.

Check that the process sees an authentication source without disclosing its value:

```bash
devplat auth status
```

## Deploy and wait for readiness

Apply the whole declaration and wait for the durable operation and live readiness:

```bash
devplat deploy apply --project orders --file application.json --wait
```

The initial response identifies an operation and revision. Reapplying the same
declaration is safe. For an update, change the image digest or specification and
apply the complete file again. To prevent silently overwriting another deployment,
pass the revision you last observed:

```bash
devplat deploy apply --project orders --file application.json --if-match 7 --wait
```

An `If-Match` conflict means another revision became current; retrieve the latest
project state through the platform UI or API, merge the intended change, and retry.
The CLI reserves standard output for results; request compact machine output with
`--output json`.

When the operation is ready, access the public service at the application URL
provided by the platform team, typically `https://web-orders.<apps-domain>` for a
public `web` component in the `orders` project. A timeout
or interrupted wait does not cancel the server-side deployment; retain the printed
operation ID and inspect it through the platform UI or API.

## Next steps

- Automate the same workflow with [CI deployment](ci-deployment.md).
- Use the [troubleshooting guide](troubleshooting.md) when a request or rollout
  fails.
- Consult the [application declaration reference](application-spec.md) for every
  supported field.
