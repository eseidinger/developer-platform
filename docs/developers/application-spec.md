# Application declaration reference

Status: current. Last reviewed October 18, 2026.

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

Service components may opt in to private Prometheus collection with
`telemetry.metrics`. See the [application contract](../architecture/application-contract.md#application-metrics-declaration-phase-4-implementation-in-progress).
Service and scheduled components may opt in to [application tracing](../architecture/application-contract.md#application-tracing-declaration-phase-4-implementation-in-progress)
with `telemetry.tracing.enabled: true`. The [tracing guide](application-tracing.md)
explains exporter authentication and framework setup.

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
    }
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
| `spec.resources` | Rejected | Stores have an independent named-resource lifecycle; bind them explicitly on the consuming component. |

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
| `bindings` | No | Up to eight approved resource references: `bindingId` UUID and optional `envPrefix` (empty, or uppercase letters/digits/underscores ending in an underscore). |

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
| `telemetry.metrics` | No | `{ "port": "http", "path": "/metrics" }`, where `port` names a declared HTTP service port and `path` is at most 128 characters with no query string. Collection uses a private Kubernetes service proxy and keeps supported HTTP series and reviewed Micrometer JVM/process metrics. |
| `telemetry.tracing.enabled` | No | Boolean, default `false`. `true` supplies a localhost OTLP endpoint and forwarder; only the forwarder mounts the short-lived Pod-bound token. |

For Spring Boot, add Actuator and the Prometheus Micrometer registry, expose
`/actuator/prometheus` on a declared service port, and use that path in the
declaration. For Quarkus, add `quarkus-micrometer-registry-prometheus` and
declare `/q/metrics`. For FastAPI, instrument requests with
[`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator)
or an equivalent library that emits `http_requests_total` and
`http_request_duration_seconds_{sum,count}` at `/metrics`. These are that library's
conventions, rather than a built-in FastAPI metric standard. The platform keeps
supported request series and fixed project/component labels; raw path, handler,
URI, user and custom metric labels are discarded. The first two
frameworks emit Micrometer's `http_server_requests_seconds_{count,sum}`;
[Spring Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
and [Quarkus Micrometer](https://quarkus.io/guides/telemetry-micrometer/)
document their setup. Project readers can use the fixed
`GET /projects/{name}/application-metrics?component={component}` view;
operators have one **Application metrics** dashboard with project, application and
component selectors. It supports both conventions, preferring Micrometer when
both are emitted by the same component. A failed scrape is reported separately
from a zero rate.

The additional **Micrometer JVM** dashboard shows heap/non-heap memory and pools,
GC pauses/allocation/pressure, CPU, threads/states, classes, buffers and file
descriptors. It selects applications that expose JVM memory metrics. The reviewed
collection allowlist includes the corresponding `jvm_*` families and selected
`process_*`/`system_*` gauges; it preserves runtime dimensions `area`, `id`, `state`,
`gc`, `action`, `cause` and `pool`. These dimensions are stripped from HTTP series.
Arbitrary metrics, runtime version metadata and custom labels remain excluded.
Existing bounds remain: 500 samples per scrape, 256 KB responses, 16 labels per
sample and 128 bytes per label value. JVM data is operator-only; the fixed
project metrics API continues to return HTTP summaries. Disabled binders and
Quarkus native executables can lack JVM series and show no data.

[OpenTelemetry HTTP semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/)
provide another, framework-neutral naming convention that FastAPI instrumentation
can use. Its metric names need an explicit mapping to this platform's supported
Prometheus series. The injected OTLP endpoint currently accepts traces only.

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
| `telemetry.tracing.enabled` | No | Boolean, default `false`; scheduled jobs start independently sampled traces. |

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
`KUBERNETES_`, `PLATFORM_`, or `OTEL_`. The platform owns OpenTelemetry settings;
use `telemetry.tracing.enabled` to opt in and configure the application exporter
using the injected endpoint. Values are strings of at most 1024 characters with
no NUL byte or key material. Names that look like passwords, tokens, API keys, or
other secrets are rejected; use the platform secrets API or UI for secret values.

Application secrets are project-scoped in the current profile and may be mounted
into every service and scheduled component in that project. Do not use the
project secret mechanism when a credential requires component-level isolation;
use a named-store component binding for managed store credentials instead. Classification is project governance metadata,
not part of this deployment declaration.

Stores are independent resources, created before an application and retained
when it is removed. There is no implicit project database or database Secret.
An administrator requests a resource binding for the exact project/component;
cross-project requests need the resource owner's approval. After the binding is
observed active, add its UUID to that component:

```json
"bindings": [{"bindingId": "11111111-1111-1111-1111-111111111111", "envPrefix": ""}]
```

Replace the sample UUID with the actual approved binding. Only that component
receives its store Secret and private lease-port egress. Multiple PostgreSQL
resources need distinct prefixes such as `PRIMARY_` and `REPORTING_` to avoid
variable collisions. Unbound components receive no database credentials/access.
Explicit configuration cannot shadow binding variables. Application credentials
rotate every 30 days with controlled restarts and at most one-hour overlap;
applications must reconnect/retry. Read-write includes application-schema DDL.

The initial PostgreSQL relay profile uses private plaintext PostgreSQL inside
SSH or the isolated network; the raw store port is not public. See the
[named-store workflow](../operators/data-stores.md) and
[human resource access](database-access.md). The old `shared-dev`/`retain` objects
in `spec.resources` are rejected; recreate declarations against this contract.

## Earlier accepted forms

Do not choose these forms for new applications. They remain accepted for unbound applications. Store consumers must use
`v1alpha2` component bindings; these forms do not provision an implicit database.

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
    "configuration": {"values": {"LOG_LEVEL": "info"}}
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
