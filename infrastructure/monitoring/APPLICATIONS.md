# Application monitoring contracts

See the [monitoring directory guide](README.md) for configuration ownership and
related contracts. Run commands from the repository root.

## Application contract

Discovery retains provisioning/failed entries, excluding empty/retired projects.
Component declarations produce targets only for public services, using
`<component>-<project>.<apps-domain>` and the declared readiness path (or `/`
for a profile). Private services and scheduled components have no public target.
Labels include project/application names, `environment=default`, component,
namespace, URL-valued instance, health profile and probe kind. Legacy
declarations retain project-host routing and status/content probes, now honoring
custom paths.

Hosted `v1alpha2` probes are `probe_kind=access-boundary`: they expect 302, 401
or 403, never follow login redirects, reject backend 200 and policy-unavailable
503, and validate public TLS. They carry no credentials and create no anonymous
route or implicit membership. A successful denial proves boundary reachability,
**not backend readiness or authorized business access**. Kubernetes HTTP
readiness and the separate `ApplicationComponentNotReady` rule supply semantic
workload health; kube-state-metrics exports bounded application/component pod
labels. Readiness on a non-public port is observed by Kubernetes, not an
invented public port mapping.

A project PUT accepts optional `probe_profile`:

- `status` (default): GET `/`, require HTTP 200.
- `hello-world`: also require the complete response body to be `hello-world`
  with optional trailing whitespace. The smoke script selects this profile.

The spec cannot supply arbitrary URLs, headers, regexes, or secrets. Additional
content contracts require a reviewed profile extension. Custom paths are bounded
ApplicationSpec inputs, not arbitrary destination URLs. A PUT is a full
specification replacement, so include `probe_profile` on subsequent updates to
retain a non-default profile. Existing catalog entries without the field use
`status` automatically; merely deploying this change does not alter their specs.

For `APPS_DOMAIN=apps.localhost`, the exporter connects to `http://proxy/` and
passes the application's hostname using the exporter `hostname` parameter. This
avoids resolving `.localhost` to the exporter container itself. It tests Caddy,
Traefik and application routing, but not public DNS or TLS.

Other application domains use `https://<name>.<APPS_DOMAIN>/`, normal DNS and
certificate validation. Redirects are disabled, responses are limited to 1 MB,
and probes time out after five seconds. Probes prefer IPv4; they do not
establish independent IPv6 availability. The exporter shares node-01's failure
domain and network perspective; this is not an outside-network availability
check.

## Lifecycle and failure handling

Provisioning writes the catalog and publishes discovery before applying workload
resources. A failed or interrupted deployment retains its target. Publishing is
atomic, serialized with provisioning/retirement by the existing PostgreSQL
advisory lock, and repeated every 30 seconds by an API background thread. This
thread reconciles monitoring files only; the separate durable deployment worker
handles accepted operations without turning discovery into workload repair.

A failed catalog query or publication retains the previous target file. The last
successful publication timestamp is exported through node-exporter's textfile
collector. The API owns the shared directory as UID 10001; Prometheus and
node-exporter mount it read-only. Compose starts the API before those readers so
the API image initializes a fresh volume's ownership. Only target identities and
publication metrics go in that volume, never API tokens or database credentials.

The shared rules cover:

- `ApplicationUnavailable`: a failed probe lasting three minutes.
- `ApplicationComponentNotReady`: an unready nonterminal project pod lasting
  three minutes, independently of public boundary success.
- `ApplicationProbeMissing`: a successful scrape with no probe result for three
  minutes.
- Existing `ScrapeTargetDown`: failed scrapes, including an unavailable
  exporter.
- `ApplicationDiscoveryStale`: missing discovery metrics, a publication
  timestamp older than two minutes, or a textfile collector error, sustained for
  three minutes.

## Security-event alerts

The API separately reads its append-only audit table through the restricted
audit reader login every 30 seconds. It publishes only bounded resource/category
counts, the latest event ID, and occurrence timestamp to the same read-only
monitoring volume. It never publishes bearer tokens, actor identities, or event
details. The shared rules alert on five authentication failures or authorization
denials against the same affected resource within 15 minutes, and immediately
report a successful privileged membership change. Each alert carries severity,
Alertmanager start time, affected resource labels, and a durable-event
reference: query `platform_security_latest_event_id` with the same labels, then
inspect that ID in `platform_audit.events` through the restricted operator
procedure.

`SecurityAuditCollectionStale` detects a failed audit-metric collector rather
than silently treating absent evidence as healthy. Prometheus also scrapes
Alertmanager; `AlertmanagerNotificationFailed` exposes its failed-delivery
counter. That alert can be affected by the same failed destination, so operators
must also inspect the counter and container logs. Alertmanager groups by alert
type and stable affected resource labels, not event ID: repeated activity stays
in one ongoing incident while the metric retains the latest supporting event.

Scrapes run every 30 seconds; rule evaluation and Alertmanager grouping add
latency. Discovery can become stale while a long provisioning request holds the
shared lock. The resulting alert identifies lack of fresh discovery, not proof
that the application is down.

There is no additional external watchdog monitor. The existing heartbeat checks
API and Prometheus readiness; it does not prove Alertmanager delivery. Watchdog
silent failure remains accepted under
[ADR-011](../../docs/architecture/decisions/ADR-011-watchdog-monitoring-boundary.md).

## Retirement

Preferred: preview, then confirm with the returned `scope_token`; the platform
deletes the namespace itself, revokes affected store access and retains
independent named-store data and the catalog.

```bash
curl -sS -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  http://127.0.0.1:8000/projects/hello/retirement-preview
# 202 retiring: repeat until 200.
curl -sS -X POST http://127.0.0.1:8000/projects/hello/retire \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"confirm_name":"hello","scope_token":"<token>"}'
```

### Manual removal (no token)

An administrator deliberately removes a project's namespace, then records
retirement using the API. A namespace that still exists (including one
terminating) blocks retirement. Kubernetes access failures also block it.
Accidental namespace loss alone never removes a monitoring target.

For an application you intend to retire, replace `hello` below and inspect its
namespace first. Namespace deletion removes all Kubernetes resources in it.
PostgreSQL data and roles outside Kubernetes are retained.

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get all,ingress
# Execute only after deciding to retire this application:
kubectl --kubeconfig .runtime/admin.kubeconfig \
  delete namespace project-hello --wait=true
# Export an authorized short-lived OIDC access token in a trusted shell
# with tracing disabled.
export PLATFORM_ACCESS_TOKEN='…'
curl --fail-with-body -X POST http://127.0.0.1:8000/projects/hello/retire \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"confirm_name":"hello"}'
```

The endpoint is idempotent, retains the catalog/spec/database/role, and removes
its target through discovery. A publication failure returns 503; the durable
retired status remains and periodic reconciliation or a repeated retirement
request completes publication. PUT explicitly reactivates a retired application.

Removing a target may resolve its existing alert; that means monitoring ended,
not that the application recovered. Record deliberate retirement separately from
outage/recovery evidence. Retirement previews, audit and provider cleanup are
implemented separately from this monitoring acknowledgement. Named-store purge
is an independent confirmed action gated by verified off-host backup intent.
