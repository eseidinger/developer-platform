# Application declaration reference

Status: current. Last reviewed October 11, 2026.

This is the developer reference for the JSON body accepted by `PUT
/projects/{name}` and by:

```bash
devplat deploy apply --project PROJECT --file application.json
```

Use **`platform.example/v1alpha2`** for new applications. It is the current,
component-based schema. The API also accepts the earlier `v1alpha1` envelope and a
flat legacy body; they are documented below only to support existing deployments.

The generated [OpenAPI contract](../api/openapi.json) is the machine-readable
source of truth. This page explains the same currently implemented constraints in
developer terms. All examples are JSON because the current CLI accepts JSON input.

Opt-in application metrics collection is a [planned Phase 4 capability](../architecture/application-contract.md#planned-application-metrics-capability-phase-4).
The current schema has no metrics field; declaring one now is rejected.
Opt-in [application tracing](../architecture/application-contract.md#planned-application-tracing-capability-phase-4)
is also planned for Phase 4; the current schema has no tracing field.

## Rules that apply to every request

- Send one complete declaration. This is a desired-state `PUT`, not a patch.
- The URL project name, `metadata.name`, and, when present, `metadata.project`
  must be the same project slug.
- A project slug or component name is 1–32 lowercase letters, digits, or hyphens;
  it starts with a letter and ends with a letter or digit.
- Unknown fields are rejected. The API returns `422` with `invalid_spec` for a
  malformed body or `unsupported_capability` for a valid-looking but unavailable
  capability.
- An image must be a public OCI image reference of 1–512 characters. The platform
  resolves accepted images to a digest. Use a digest yourself when reproducibility
  matters; private image pull credentials are not supported.
- `If-Match` is optional but recommended for updates. Pass the current revision to
  avoid overwriting another deployment; a stale revision returns `409`.

## Current schema: `platform.example/v1alpha2`

### Complete shape

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
          "image": "ghcr.io/acme/orders:2026.10.07",
          "command": ["./orders"],
          "args": ["serve"]
        },
        "ports": [
          {"name": "http", "protocol": "http", "port": 8080}
        ],
        "replicas": 2,
        "exposure": "public",
        "resources": {
          "requests": {"cpu": "250m", "memory": "256Mi"},
          "limits": {"cpu": "500m", "memory": "512Mi"}
        },
        "health": {"readiness": {"profile": "status"}},
        "outbound": [
          {"cidr": "198.51.100.0/24", "port": 443}
        ]
      },
      {
        "name": "nightly-report",
        "type": "scheduled",
        "runtime": {
          "type": "container",
          "image": "ghcr.io/acme/orders:2026.10.07",
          "args": ["report"]
        },
        "schedule": "0 2 * * *",
        "timeZone": "UTC",
        "concurrencyPolicy": "Forbid"
      }
    ],
    "configuration": {
      "values": {"LOG_LEVEL": "info"}
    },
    "resources": [
      {"name": "database", "type": "postgres", "profile": "shared-dev", "deletionPolicy": "retain"}
    ]
  }
}
```

The example illustrates common optional fields; the tables below list the full
supported set. It will only be accepted when the
project quota permits its resources and replicas, and the platform operator has
allowed the shown outbound CIDR and port. Omit `outbound` unless the operator has
approved it.

### Top-level and metadata fields

| Field | Required | Accepted value |
| --- | --- | --- |
| `apiVersion` | Yes | Exact string `platform.example/v1alpha2`. |
| `kind` | Yes | Exact string `Application`. |
| `metadata.name` | Yes | Project slug. Must equal the URL project name. |
| `metadata.project` | No | If present, must equal `metadata.name`. |
| `metadata.environment` | No | Only `default`. |
| `spec.components` | Yes | Array of 1–5 service or scheduled components. Names must be unique. |
| `spec.configuration` | No | Object containing only `values`; described below. |
| `spec.resources` | No | At most one PostgreSQL declaration; described below. A project database is provisioned by the current platform profile regardless. |

### Fields shared by all components

| Field | Required | Accepted value |
| --- | --- | --- |
| `name` | Yes | Unique component slug. |
| `type` | Yes | `service` or `scheduled`. |
| `runtime.type` | Yes | Exact string `container`. |
| `runtime.image` | Yes | Public OCI image reference. |
| `runtime.command` | No | Array of up to 20 strings; replaces the image command. |
| `runtime.args` | No | Array of up to 50 strings; supplies command arguments. |
| `resources` | No | Resource requests and limits; see [Resource limits](#resource-limits). |

### `service` component fields

| Field | Required | Accepted value |
| --- | --- | --- |
| `ports` | Conditional | Array of up to 10 HTTP ports. Required for a public service; optional for a private service. |
| `ports[].name` | Yes when `ports` is used | 1–15 lowercase letters, digits, or hyphens; starts with a letter. |
| `ports[].protocol` | Yes when `ports` is used | Exact string `http`. |
| `ports[].port` | Yes when `ports` is used | Integer from 1024 through 65535. Port names must be unique within the component. |
| `replicas` | No | Integer from 1 through 5; default `1`. Subject to the project quota. |
| `exposure` | No | `private` (default) or `public`. At most one service in an application can be public. |
| `health.readiness` | No | Exactly one of `profile` or `path`. `profile` is `status` or `hello-world` and retains the TCP readiness probe on the first declared port. `path` configures an HTTP GET readiness probe; it must begin with `/` and uses the first declared port unless `port` matches another declared port number. |
| `outbound` | No | Up to five `{ "cidr": "…", "port": N }` or `{ "dns": "api.example.com", "port": N }` destinations. CIDRs, and every IP address currently resolved for DNS destinations, must be in the operator allow-list. DNS rules are resolved to fixed NetworkPolicy IP rules when the deployment is applied; reapply when the destination address changes. |

A public service gets an ingress at
`https://<component>-<project>.<apps-domain>`. Private services get in-project
DNS and can be reached by other project workloads through their component name.

Public `v1alpha2` ingress always traverses the platform authentication and
authorization boundary. Readiness or `exposure: public` does not authorize a
caller: without an active access policy, public access is denied. A project
administrator creates groups and a separate `ApplicationAccessPolicy` selecting
`browser-session` or `bearer-token`, allowed groups, and explicit non-overlapping
paths/methods. Human access requires approval/group assignment after first login;
machine access requires provider approval before credential activation. Platform
roles and CI deployment credentials do not imply application membership.

Use the [hosted application API guide](api.md#hosted-application-access) for the
separate policy, membership, service-access, and governance resources. Do not put
OIDC clients, audiences, redirect URIs, group mappings, or credentials into this
declaration. Anonymous public routes and direct access to the public backend,
including from other components in the same project, are unsupported. Private
services retain in-project connectivity. Applications read the
[trusted principal headers](../architecture/security-and-authorization.md#upstream-identity-transport);
they need only any finer domain-level authorization. Legacy single-service
declarations retain their existing routing and must migrate to `v1alpha2` for
hosted protection.

### `scheduled` component fields

| Field | Required | Accepted value |
| --- | --- | --- |
| `schedule` | Yes | Five-field cron expression. Each field supports `*`, a number, an increasing numeric range, comma-separated values, and a `/step`. |
| `timeZone` | No | Only `UTC`; default `UTC`. |
| `concurrencyPolicy` | No | Only `Forbid`; default `Forbid`. This prevents overlapping runs. |
| `retryLimit` | No | Integer 0–10; default `6`. Kubernetes retries a failed Job with exponential backoff. This does not establish dependency ordering. |
| `maxRunSeconds` | No | Integer 60–86400. Stops a Job that exceeds this duration. |
| `outbound` | No | Same CIDR or DNS TCP egress declaration supported by service components. |

Scheduled components do not accept `ports`, `replicas`, `exposure`, or `health`.

Public monitoring uses the component hostname and declared health path, with no
target for private-only applications. For protected `v1alpha2` services it checks
the authentication boundary's expected denial/login response, not backend content;
Kubernetes readiness is the independent semantic health signal. It never creates
an anonymous health route or implicitly authorizes a monitoring identity.
Applications may emit the domain-neutral
[operational log envelope](../../infrastructure/monitoring/README.md#central-workload-logs-and-correlation)
for seven-day configured central retention and authorized retained-log reads.
This does not add a declaration field; normal free-text logs stay kubelet-only.

For an application such as Spring Boot that becomes reachable before its database
migrations and initialization are complete, use its application readiness endpoint:

```json
"health": {"readiness": {"path": "/actuator/health/readiness"}}
```

This makes Kubernetes withhold the Service endpoint until the endpoint returns a
successful response. It does not order a scheduled Job after the service; clients
must still retry transient connection failures.

Every service with a declared port also receives a platform-managed TCP startup
probe. It allows up to three minutes for the container to bind its first port
before liveness and readiness failures are enforced. Startup-probe timing is not
currently configurable in the application schema.

### Resource limits

`resources` is optional on each component. If omitted, the platform applies:

```json
{
  "requests": {"cpu": "100m", "memory": "128Mi"},
  "limits": {"cpu": "500m", "memory": "256Mi"}
}
```

When supplied, it may contain only `requests` and `limits`, each containing only
`cpu` and `memory`. Missing individual values inherit the defaults.

| Resource | Requests maximum | Limits maximum | Accepted syntax |
| --- | ---: | ---: | --- |
| CPU | 1 CPU | 2 CPU | Millicores such as `250m`, or decimal cores such as `0.25`. |
| Memory | 1 GiB | 2 GiB | Mebibytes or gibibytes, such as `256Mi` or `1Gi`. |

Every value must be positive and each request must be less than or equal to its
corresponding limit. The effective namespace quota can be lower and must also fit
the requested replica count plus rolling-update surge capacity.

### Configuration and database declaration

`spec.configuration.values` is a map of up to 50 non-secret environment values.
Names use `[A-Za-z_][A-Za-z0-9_]{0,62}` and must not start with `PG`,
`KUBERNETES_`, or `PLATFORM_`. Values are strings of at most 1024 characters with
no NUL byte or key material. Names that look like passwords, tokens, API keys, or
other secrets are rejected; use the platform secrets API or UI for secret values.

Application secrets are project-scoped in the current profile and may be mounted
into every service and scheduled component in that project. Do not use the
project secret mechanism when a credential requires component-level isolation;
that capability is not supported. Classification is project governance metadata,
not part of this deployment declaration.

`spec.resources`, if declared, may contain one object only:

```json
{"name": "database", "type": "postgres", "profile": "shared-dev", "deletionPolicy": "retain"}
```

No other resource type, PostgreSQL profile, or deletion policy is accepted. The
current profile always provisions the project PostgreSQL database and injects its
connection values through `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and
`PGPASSWORD`.

In the initial lab profile, application-to-PostgreSQL traffic is not TLS-protected;
the cross-project encrypted-channel requirement covers public HTTPS instead.
See the [generic integration profile](../architecture/application-contract.md#generic-cross-project-integration-profile)
for this limit and the separate governance/retention responsibilities.

## Earlier accepted forms

Do not choose these forms for new applications. They remain accepted for existing
projects and map to the same desired-state deployment behavior.

### `platform.example/v1alpha1`

The earlier envelope has the same top-level `apiVersion`, `kind`, and `metadata`
rules, but `spec` contains a single `application` object instead of `components`:

```json
{
  "apiVersion": "platform.example/v1alpha1",
  "kind": "Application",
  "metadata": {"name": "orders"},
  "spec": {
    "application": {
      "runtime": {"type": "container", "image": "ghcr.io/acme/orders:2026.10.07"},
      "endpoints": [{"name": "http", "protocol": "http", "port": 8080, "exposure": "public"}],
      "scaling": {"minInstances": 1, "maxInstances": 1},
      "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}},
      "health": {"readiness": {"profile": "status"}}
    },
    "configuration": {"values": {"LOG_LEVEL": "info"}},
    "resources": [{"name": "database", "type": "postgres", "profile": "shared-dev", "deletionPolicy": "retain"}]
  }
}
```

`runtime` is required. `endpoints` is optional but, when present, has exactly one
public HTTP endpoint. `scaling` is optional but only accepts exactly one instance.
The resource, configuration, health, image, and resource-limit rules are the same
as `v1alpha2`.

### Flat legacy body

The legacy form has no `apiVersion` or `kind`:

```json
{
  "name": "orders",
  "image": "ghcr.io/acme/orders:2026.10.07",
  "port": 8080,
  "probe_profile": "status",
  "resources": {
    "requests": {"cpu": "250m", "memory": "256Mi"},
    "limits": {"cpu": "500m", "memory": "512Mi"}
  },
  "configuration": {"LOG_LEVEL": "info"}
}
```

`name` and `image` are required. `port` defaults to `8080` and must be 1024–65535;
`probe_profile` defaults to `status` and accepts `status` or `hello-world`.
`resources` and `configuration` follow the same validation rules above. Components
cannot be expressed in the flat form.

## Validate before deploying

The CLI validates that the file is JSON and lets the API validate the schema:

```bash
devplat deploy apply --project orders --file application.json --if-match 7 --wait --output json
```

For a capability view specific to the deployed platform, request
`GET /v1/capabilities` with your access token. Use the response and a `422` error's
stable `code` as the final authority when the platform's operator policy differs
from the defaults in this reference.
