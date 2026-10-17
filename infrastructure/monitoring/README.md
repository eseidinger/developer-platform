# Application availability monitoring

This source-adjacent guide documents monitoring generation and validation. Use
the [operator monitoring guide](../../docs/operators/monitoring.md) for live
operations and the [maintainer monitoring guide](../../docs/maintainers/monitoring.md)
for implementation ownership.

The platform API publishes application targets from PostgreSQL to a shared
`monitoring_discovery` volume. Prometheus reads `applications.json` with file
service discovery and probes each target through the blackbox exporter. Target
changes do not require a Prometheus restart. Alertmanager uses its existing
configured receiver; the repository's `local-only` default does not send email.

## Application contract

Discovery retains provisioning/failed entries, excluding empty/retired projects.
Component declarations produce targets only for public services, using
`<component>-<project>.<apps-domain>` and the declared readiness path (or `/` for
a profile). Private services and scheduled components have no public target.
Labels include project/application names, `environment=default`, component,
namespace, URL-valued instance, health profile and probe kind. Legacy declarations
retain project-host routing and status/content probes, now honoring custom paths.

Hosted `v1alpha2` probes are `probe_kind=access-boundary`: they expect 302, 401 or
403, never follow login redirects, reject backend 200 and policy-unavailable 503,
and validate public TLS. They carry no credentials and create no anonymous route
or implicit membership. A successful denial proves boundary reachability, **not
backend readiness or authorized business access**. Kubernetes HTTP readiness and
the separate `ApplicationComponentNotReady` rule supply semantic workload health;
kube-state-metrics exports bounded application/component pod labels. Readiness on
a non-public port is observed by Kubernetes, not an invented public port mapping.

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
- `ApplicationComponentNotReady`: an unready nonterminal project pod lasting
  three minutes, independently of public boundary success.
- `ApplicationProbeMissing`: a successful scrape with no probe result for three minutes.
- Existing `ScrapeTargetDown`: failed scrapes, including an unavailable exporter.
- `ApplicationDiscoveryStale`: missing discovery metrics, a publication timestamp
  older than two minutes, or a textfile collector error, sustained for three minutes.

## Central workload logs and correlation

Alloy discovers project pods and reads logs over the TLS-verified Kubernetes API
using a dedicated `workload-log-reader` service account. Its cluster-wide
administrative RBAC allows only pod get/list/watch and pod-log get: no secrets,
exec, or mutations. Target filters exclude system/access namespaces. It uses
neither the provisioner credential nor host pod-filesystem mounts. Bootstrap
creates `.runtime/log-reader.kubeconfig`; like the controller credential its file
is container-readable under the private `.runtime` directory and mounted only
into the trusted collector. Revoke by deleting `workload-log-reader-token` and
rebootstrap. Never share that file or mount it into a workload.

The collector runs as UID `0` (for the existing host Docker-log reader) and GID
`473`, matching the pinned Alloy image's `473:473`, mode `0770` state directory.
Its named volume stays mounted at `/var/lib/alloy`; no ownership migration,
world-writable permissions, extra capabilities or privileged container is needed.
The root filesystem remains read-only with all capabilities dropped and
`no-new-privileges`. Changing the pinned image requires rechecking this group and
the production-volume fixture, not assuming root can bypass permissions.
Alloy has an internal `/-/ready` health check and bootstrap waits up to 120 seconds
for it. API/Prometheus readiness alone is not collector readiness; even a healthy
collector does not prove successful ingestion or elapsed log retention.

Kubernetes operational logs use `job=kubernetes-workloads`, project, default
environment, application, component, namespace, pod and container labels. Newly
deployed/restarted workloads carry platform-derived pod annotations for revision
and operation ID; Alloy moves those to non-indexed structured metadata. Existing
pods need an ordinary reapply/restart to obtain that metadata. Prometheus never
uses operation/correlation IDs as metric labels.

Only this minimized JSON envelope enters centralized workload storage:

```json
{"event":"request.completed","level":"info","correlationId":"0123456789abcdef0123456789abcdef"}
```

Events are `application`, `request`, or `job` followed by `.started`, `.ready`,
`.completed`, or `.failed`. Levels are debug/info/warning/error. Correlation is
optional/empty or an opaque lowercase UUID/32-hex identifier supplied and
propagated by applications. It is not a domain identifier interpreted by the
platform. Owners must classify it as Internal or explicitly approved Confidential;
do not put customer identifiers or secrets into it. Unknown fields are discarded;
malformed JSON, free text, invalid envelopes and lines over 4 KB are dropped
before storage.
This intentionally does not promise central retention of arbitrary debug logs.
The existing kubelet log endpoint remains available for best-effort diagnostics
with best-effort redaction. The collector cannot infer whether an otherwise
well-shaped application-supplied identifier was classified correctly.

Loki's persistent volume and compactor enforce the configured 168-hour retention.
Alloy stores file positions in its own persistent volume. Collection/write
outages may lose logs; neither retention nor a volume is a delivery guarantee.
Loki/Grafana remain operator-only, with no tenant access to shared queries.
`GET /projects/{name}/retained-logs` requires the existing project view permission,
fixes the project/namespace selector server-side, supports bounded time/component/
pod filters, revalidates returned streams/envelopes, and audits the read. It never
accepts LogQL or returns raw backend diagnostics. Backend failure is unavailable,
not an empty-success result; retention state `configured` is not live acceptance.

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
silent failure remains accepted under [ADR-011](../../docs/architecture/decisions/ADR-011-watchdog-monitoring-boundary.md).

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
uv sync --project platform/app
uv run --project platform/app python -m unittest discover -s platform/app/tests -v
python3 scripts/check-monitoring.py
python3 scripts/check-workload-logs.py
docker compose config --quiet
```

The fixture script requires Linux Docker on the local Unix socket and OpenSSL.
It starts temporary loopback HTTP/TLS servers, a blackbox exporter and Prometheus,
then removes those containers. It validates production configuration/rules, status,
content, redirect, timeout, certificate rejection, recovery, target labels and
live discovery removal. The workload-log fixture uses real pinned Alloy/Loki and
a TLS-verified fake Kubernetes API to verify discovery/source, safe ingestion,
scope, structured metadata and Loki restart readback. It reproduces the old
UID/GID permission failure, then uses production hardening and a fresh named
state volume at `/var/lib/alloy` to verify collector readiness and restart.
Both remove their containers (and the workload fixture's exact temporary volume),
never deploy the platform and send no notifications. Neither proves seven elapsed
days of retention or real-cluster behavior.
API lifecycle tests use simulated PostgreSQL/Kubernetes dependencies; they do not
establish real cluster deletion or notification delivery.

For a fresh local platform, follow the [quick start](../../README.md#quick-start).
For an existing installation, after other drills finish and with no provisioning
request in progress, deploy the changed source and recreate the affected services:

```bash
bash scripts/up.sh
```

The exporter has no published host port. In Prometheus at `http://localhost:9090`,
check Targets and query `probe_success{job="applications"}`. For protected
components, also inspect Kubernetes readiness; a successful boundary denial is
not workload health. Check
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

Deployed evidence now exists for component boundary probes, independent
Kubernetes readiness and immediate provider/consumer central correlation reads:
operator-provided node-01 run `60c3ca1647b9` passed all 45 assertions with
`--timed --monitoring` after the collector state-permission repair. See
[EV-46](../../docs/operators/validation/access-and-authorization.md#executed-hosted-access-monitoring-acceptance-october-11-2026).
The report says `sevenDayRetention: not-time-verified`; neither post-retirement
log readback nor elapsed retention/compactor deletion was exercised.

Use the neutral hosted-access harness with `--monitoring` and a newly published
fixture digest. It verifies component URLs/probes, Kubernetes readiness and safe
provider/consumer central correlation before retirement. It does not remove the
full monitoring/retention deferral: record an operational event, confirm readback
after pod retirement/restart, and verify retention around the seven-day boundary
including compactor deletion delay. Record collector/backend health and gaps.
Keep PLAN-017 open until the remaining readback and retention acceptance are recorded.

After the backup drills finish, verify the public smoke probe, then temporarily
scale its deployment to zero and confirm the application alert reaches the
intended inbox. Restore the original replica count and confirm readiness, the
successful probe, and the recovery email. Record revision, target, original
replicas, failure/recovery and receipt times. Test retirement separately on an
intentionally disposable application. Local fixtures do not close OPS-007-T01.

## Workload CPU and memory capacity

**Workloads and capacity** has a project-namespace selector and pod/deployment
comparisons of CPU usage (cores), memory working set (bytes), configured requests,
and configured limits. CPU usage needs at least two scrapes in its five-minute
rate window. Deployment totals join Pod → ReplicaSet → Deployment ownership, so
rolling ReplicaSets are grouped together; scheduled jobs remain visible as pods.
Only Pending, Running and Unknown pods contribute to current resource totals.
Historical samples remain available over the selected time range.

Requests and limits are steady-state container sums, including native restartable
init sidecars (`restartPolicy: Always`). Ordinary sequential init containers and
pod overhead are excluded: these panels do not claim the scheduler's effective
peak startup requirement. A limit is omitted when any contributing container or
deployment pod lacks a positive limit; missing limits never mean zero capacity.
Host panels continue to show the whole host, independently of namespace selection.

Prometheus discovers all nodes through the TLS-verified Kubernetes API and scrapes
private kubelet HTTPS `/metrics/cadvisor` endpoints using a separate
`capacity-metrics-reader` service account. It can list/watch nodes and get
`nodes/metrics`; it cannot proxy nodes, exec, read secrets or mutate workloads.
The cluster CA verifies both discovery and kubelet serving certificates. Bootstrap
extracts `.runtime/capacity-reader.token` and `.runtime/capacity-reader-ca.crt`,
mounting them only into Prometheus; the token has the existing UID 65534 read ACL.
Revoke by deleting `capacity-metrics-reader-token` and rebootstrap to reissue it.

Only `container_cpu_usage_seconds_total` and
`container_memory_working_set_bytes` for named project containers are retained;
sandbox containers and arbitrary labels are discarded. Scrapes are bounded to
10,000 retained samples and a 16 MB response per node. The **Container usage
collection** panel and existing scrape alerts expose collection failures; missing
usage is not synthesized as healthy zero. Recording rules in `capacity-rules.yaml`
combine these metrics with kube-state-metrics resource and ownership data.

`scripts/check-monitoring.py` validates the configuration and executes
`tests/capacity.test.yaml`: it covers namespace isolation, rolling ReplicaSets,
sidecars, ordinary init exclusion, completed jobs, and incomplete limits.

## PostgreSQL and host storage

The operator-only **PostgreSQL** dashboard selects one database for connections,
transactions/rollbacks, size, cache hits, temporary files, deadlocks, locks and
oldest transactions. Shared connection usage/limit, uptime and collection health
are explicitly server-wide and independent of the database selector. A database
limit of `-1` means no separate limit and is not plotted as zero capacity. Idle
databases can have no cache-hit ratio until block activity occurs.

`postgres-exporter` is pinned to v0.20.1, has no published host port, and runs
read-only with all capabilities dropped, 128 MiB memory and 0.25 CPU limits.
Prometheus keeps only reviewed aggregate metrics and database/state/lock-mode
labels, with a 5,000-sample, 2 MB scrape budget. Table, user, application-name,
query-text, query-ID and replication-client collectors are disabled. The fixed
`postgres-queries.yaml` aggregates connection states, lock waits and transaction
ages in SQL before export, avoiding collisions and sensitive session labels from
the stock activity collector. It uses the pinned exporter's deprecated custom
query option; revalidate compatibility before upgrading. The shared exporter has no per-table labels. The Phase 7 collector below adds
aggregate named-database vacuum/dead-tuple observations.

Bootstrap runs `scripts/setup-postgres-monitoring.py` after PostgreSQL is healthy.
It reconciles `platform_monitor` with `pg_monitor`, five connections maximum,
read-only default transactions and a five-second statement timeout. It receives
no application-table grants, superuser, role/database creation, replication or
RLS bypass privileges. The shared exporter connects to `platform` for catalog statistics. The additional
Phase 7 collector receives CONNECT to retained named PostgreSQL databases for
aggregate statistics; neither collector uses application credentials or table-data grants. `pg_monitor` is a trusted operator role able to read cluster
statistics; never expose its credential to projects or AI tools.

Run `python3 scripts/init.py` to generate `POSTGRES_MONITOR_PASSWORD` in `.env`,
including on an existing installation. Setup writes
`.runtime/postgres-monitor.password` with a UID 65534 read ACL, mounted only into
the exporter; the password is neither a Compose environment variable nor a DSN
argument. `.env` remains part of the existing protected configuration backup;
the runtime file is regenerated. To rotate, replace the configured secret,
rerun setup and recreate only `postgres-exporter`. To revoke, disable the
`platform_monitor` login and stop the exporter. The private Docker connection
uses the existing PostgreSQL transport (`sslmode=disable`); it adds no public
PostgreSQL or exporter route.

**Workloads and capacity** also displays host disk-space utilization, total and
available bytes, and inode utilization. These panels use node exporter, exclude
virtual filesystems, and are independent of project selection. Space utilization
uses capacity minus space available to an unprivileged process, including reserved
blocks. Filesystems without inode capacity have no inode ratio.

`scripts/check-postgres-monitoring.py` creates disposable PostgreSQL 18, exporter
and Prometheus containers. It verifies repeatable role setup, denied application
reads/writes, aggregate privacy, database selection, absent/unlimited values and
dashboard query readback using production collectors, SQL and metric filters.


## Phase 7 store performance

The named-resource overview links to PostgreSQL, RustFS S3, OpenSearch, Qdrant,
Apache AGE, pgvector, DuckDB/Parquet and dedicated Neo4j Community dashboards.
Regenerate reviewed definitions with `python3 scripts/generate-dashboards.py`.
Native collection runs independently of lifecycle reconciliation and publishes
bounded textfile metrics through the existing node exporter. Last-good readings
remain visible after failure, with separate collection health/freshness. The
operator-only dedicated-instance controller reads Docker statistics; API/relay
containers do not receive its Docker socket. This operator service has host-level
Docker authority and must be restricted to the fixed API source and private key.

OpenSearch uses the `platform_monitor` native role for selected cluster/index
statistics, with document and identity administration denied. Qdrant uses the
separate `STORE_MONITOR_PASSWORD` as a native read-only key for metrics; its
edition does not provide a metrics-only key, so keep that operator credential
private. Resource mappings come from the catalog, not arbitrary native labels.
The native collector prepares OpenSearch's restricted monitoring account once per
process before collecting, including on an installation with no named resources.
Failed setup is retried on the next pass; subsequent statistics requests use the
restricted account, without requiring a project to provision an index first.
RustFS 1.0.2 exports metrics over OTLP/HTTP to Alloy's private port 4320; the
allowlist aggregates away unreviewed dimensions before export. Its object keys,
paths, logs and trace payloads do not enter this new metrics pipeline.

The PostgreSQL dashboard now includes shared WAL/checkpoint statistics. The
separate collector connects read-only as `platform_monitor` to named databases,
at most eight per pass, and publishes aggregate table/vacuum/vector-index and
index-build statistics without SQL, user or index-name labels. Named-resource
provisioning grants this operator identity CONNECT when present; prepare existing
named databases through reviewed operator maintenance. These additions extend
the earlier platform-only exporter scope described above.

AGE/pgvector/Neo4j query latency and DuckDB/job profiling require explicit
application instrumentation. The [collector example and integration guide](../../examples/store-observability/README.md)
opens no listener and returns Prometheus text for an application's existing
protected metrics route. Enable the normal application metrics opt-in; its
reviewed allowlist now accepts these bounded metric families. Only numeric
DuckDB profile fields are exported. Missing application observations are unknown,
not proof of zero traffic or completed external integration. Shared-server
CPU/I/O is labeled separately from attributable resource/workload signals.

Run `scripts/verify-store-metric-pipeline.py` for real signed RustFS I/O through
production Alloy into disposable Prometheus, sensitive-dimension exclusion and
parsing all store-dashboard queries. Native OpenSearch/Qdrant fixtures additionally
verify collector permissions and release-specific metric schemas. Alert fixtures
include `tests/native-stores.test.yaml`; thresholds are operational starting
points to tune against observed workloads, not store-adoption requirements.

Neo4j Community's pinned image includes a checksum-verified standard JVM agent;
heap, live threads and normalized GC seconds do not require Enterprise metrics.
The agent flag is set once in the image configuration: passing it through the
entrypoint's repeatable environment setting broke restarts by duplicating it.
Native JVM collection and clean restart are fixture-verified. A separate private
relay scrape exposes aggregate resource connection counts without credential IDs.
The operator controller also reattaches replaced infrastructure to running owned
instance networks; it never starts retired/stopped instances.

Collection timestamps/health remain separate from retained last-good values.
PostgreSQL resource health includes never-sampled and failed database attempts;
its bounded round robin must not be mistaken for continuous per-resource sampling.
Run `examples/store-observability/verify.py` with the optional analytics fixture
group for actual DuckDB profiling and numeric-only export evidence.
