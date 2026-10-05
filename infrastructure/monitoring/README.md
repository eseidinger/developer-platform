# Application availability monitoring

The platform API publishes application targets from PostgreSQL to a shared
`monitoring_discovery` volume. Prometheus reads `applications.json` with file
service discovery and probes each target through the blackbox exporter. Target
changes do not require a Prometheus restart. Alertmanager uses its existing
configured receiver; the repository's `local-only` default does not send email.

## Application contract

Every catalog entry is monitored, including `provisioning` and `failed` entries.
Only explicit `retired` entries are excluded. Each target has `project`,
`application`, `namespace`, and URL-valued `instance` labels. Project names are the
current stable identifiers; the richer project/environment identity model is
still future work.

A project PUT accepts optional `probe_profile`:

- `status` (default): GET `/`, require HTTP 200.
- `hello-world`: also require the complete response body to be `hello-world`
  with optional trailing whitespace. The smoke script selects this profile.

The spec cannot supply arbitrary URLs, headers, regexes, or secrets. Additional
paths/content contracts require a reviewed profile extension. A PUT is a full
specification replacement, so include `probe_profile` on subsequent updates to
retain a non-default profile. Existing catalog entries without the field use
`status` automatically; merely deploying this change does not alter their specs.

For `APPS_DOMAIN=apps.localhost`, the exporter connects to `http://proxy/` and
passes the application's hostname using the exporter `hostname` parameter.
This avoids resolving `.localhost` to the exporter container itself. It tests
Caddy, Traefik and application routing, but not public DNS or TLS.

Other application domains use `https://<name>.<APPS_DOMAIN>/`, normal DNS and
certificate validation. Redirects are disabled, responses are limited to 1 MB,
and probes time out after five seconds. Probes prefer IPv4; they do not establish
independent IPv6 availability. The exporter shares node-01's failure domain and
network perspective; this is not an outside-network availability check.

## Lifecycle and failure handling

Provisioning writes the catalog and publishes discovery before applying workload
resources. A failed or interrupted deployment retains its target. Publishing is
atomic, serialized with provisioning/retirement by the existing PostgreSQL
advisory lock, and repeated every 30 seconds by an API background thread. This
thread reconciles monitoring files only; it does not repair workloads or provide
a durable provisioning worker.

A failed catalog query or publication retains the previous target file. The last
successful publication timestamp is exported through node-exporter's textfile
collector. The API owns the shared directory as UID 10001; Prometheus and
node-exporter mount it read-only. Compose starts the API before those readers so
the API image initializes a fresh volume's ownership. Only target identities and
publication metrics go in that volume, never API tokens or database credentials.

The shared rules cover:

- `ApplicationUnavailable`: a failed probe lasting three minutes.
- `ApplicationProbeMissing`: a successful scrape with no probe result for three minutes.
- Existing `ScrapeTargetDown`: failed scrapes, including an unavailable exporter.
- `ApplicationDiscoveryStale`: missing discovery metrics, a publication timestamp
  older than two minutes, or a textfile collector error, sustained for three minutes.

## Security-event alerts

The API separately reads its append-only audit table through the restricted audit
reader login every 30 seconds. It publishes only bounded resource/category counts,
the latest event ID, and occurrence timestamp to the same read-only monitoring
volume. It never publishes bearer tokens, actor identities, or event details.
The shared rules alert on five authentication failures or authorization denials
against the same affected resource within 15 minutes, and immediately report a
successful privileged membership change. Each alert carries severity, Alertmanager
start time, affected resource labels, and a durable-event reference: query
`platform_security_latest_event_id` with the same labels, then inspect that ID in
`platform_audit.events` through the restricted operator procedure.

`SecurityAuditCollectionStale` detects a failed audit-metric collector rather than
silently treating absent evidence as healthy. Prometheus also scrapes Alertmanager;
`AlertmanagerNotificationFailed` exposes its failed-delivery counter. That alert can
be affected by the same failed destination, so operators must also inspect the
counter and container logs. Alertmanager groups by alert type and stable affected
resource labels, not event ID: repeated activity stays in one ongoing incident
while the metric retains the latest supporting event.

Scrapes run every 30 seconds; rule evaluation and Alertmanager grouping add
latency. Discovery can become stale while a long provisioning request holds the
shared lock. The resulting alert identifies lack of fresh discovery, not proof
that the application is down.

There is no additional external watchdog monitor. The existing heartbeat checks
API and Prometheus readiness; it does not prove Alertmanager delivery. Watchdog
silent failure remains accepted under [ADR-011](../../docs/03-decisions/ADR-011-watchdog-monitoring-boundary.md).

## Retirement

Preferred: preview, then confirm with the returned `scope_token`; the platform deletes
the namespace itself and keeps the database, role and catalog.

```bash
curl -sS -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" http://127.0.0.1:8000/projects/hello/retirement-preview
curl -sS -X POST http://127.0.0.1:8000/projects/hello/retire \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" -H 'Content-Type: application/json' \
  --data '{"confirm_name":"hello","scope_token":"<token>"}'   # 202 retiring: repeat until 200
```

### Manual removal (no token)

An
administrator deliberately removes a project's namespace, then records retirement
using the API. A namespace that still exists (including one terminating) blocks
retirement. Kubernetes access failures also block it. Accidental namespace loss
alone never removes a monitoring target.

For an application you intend to retire, replace `hello` below and inspect its
namespace first. Namespace deletion removes all Kubernetes resources in it.
PostgreSQL data and roles outside Kubernetes are retained.

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get all,ingress
# Execute only after deciding to retire this application:
kubectl --kubeconfig .runtime/admin.kubeconfig delete namespace project-hello --wait=true
# Export an authorized short-lived OIDC access token in a trusted shell with tracing disabled.
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
outage/recovery evidence. This acknowledgement endpoint does not implement the
planned deletion preview, audit history, durable cleanup jobs, or database purge.

## Local preparation and validation

Install test dependencies in a virtual environment, then run:

```bash
pip install -r platform/tests/requirements.txt
python3 -m unittest discover -s platform/tests -v
python3 scripts/check-monitoring.py
docker compose config --quiet
```

The fixture script requires Linux Docker on the local Unix socket and OpenSSL.
It starts temporary loopback HTTP/TLS servers, a blackbox exporter and Prometheus,
then removes those containers. It validates production configuration/rules, status,
content, redirect, timeout, certificate rejection, recovery, target labels and
live discovery removal. It never deploys the platform or sends notifications.
API lifecycle tests use simulated PostgreSQL/Kubernetes dependencies; they do not
establish real cluster deletion or notification delivery.

For a fresh local platform, follow the [quick start](../../README.md#quick-start-on-ubuntu--wsl2).
For an existing installation, after other drills finish and with no provisioning
request in progress, deploy the changed source and recreate the affected services:

```bash
docker compose up -d --build --force-recreate platform-api blackbox-exporter prometheus node-exporter
```

The exporter has no published host port. In Prometheus at `http://localhost:9090`,
check Targets and query `probe_success{job="applications"}`. Check
`platform_discovery_last_success_timestamp_seconds` and confirm labels identify
the intended application. Retained discovery volumes rebuild from the current
catalog at API startup; a fresh empty catalog publishes an empty target list.

The volume is disposable derived state. Project specs (including profiles) and
retired status remain in the existing PostgreSQL backup; source includes exporter
and alert configuration. No additional secret or independent backup of discovery
files is needed. A restore rebuilds them against the restored installation's
`APPS_DOMAIN`. Explicitly selecting a retired project for restore/reapply via PUT
reactivates it; automatic bulk reapply should skip retired catalog entries.

## Live acceptance still required

After the backup drills finish, verify the public smoke probe, then temporarily
scale its deployment to zero and confirm the application alert reaches the
intended inbox. Restore the original replica count and confirm readiness, the
successful probe, and the recovery email. Record revision, target, original
replicas, failure/recovery and receipt times. Test retirement separately on an
intentionally disposable application. Local fixtures do not close OPS-007-T01.
