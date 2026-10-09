# Platform runbooks

Status: current administrator procedures reviewed against source.
Run commands from the repository root on the affected host. An Ansible
installation requires a privileged shell in `/opt/developer-platform`.

Use these procedures for shared services, capacity, policy, availability, and backup incidents. Preserve logs and redact credentials before sharing evidence.

## Inspect the current installation

```bash
docker compose ps
curl --fail-with-body http://127.0.0.1:8000/healthz
curl --fail-with-body http://127.0.0.1:8000/readyz
curl --fail-with-body http://127.0.0.1:9090/-/ready
docker compose exec -T postgres pg_isready -U postgres -d platform
kubectl --kubeconfig .runtime/admin.kubeconfig get nodes -o wide
kubectl --kubeconfig .runtime/admin.kubeconfig get pods -A
```

`/healthz` is process health; `/readyz` executes a SQL query and reads the `platform-system` namespace using the controller credential. It does not check every node or workload. PostgreSQL readiness is not a data-integrity or application-permission check. Record time, host, code revision (`git rev-parse HEAD`), affected project, latest spec, and observed symptoms. The API persists desired revisions and operations; authorized operation reads include a live readiness snapshot, while the project catalog status remains an apply/lifecycle state. Preserve available logs and redact credentials before sharing them.

## Controlled PostgreSQL outage and recovery

`ansible/test-platform-postgres-outage.yml` is a self-contained protected-lab drill. It creates a disposable project,
developer persona, and database-bound `http-echo` workload; stops only the Compose PostgreSQL service; requires the
safe authenticated outage response (`503` while authorization cannot reach PostgreSQL, or `DatabaseUnavailable` when
the endpoint can report it) and a failed Platform API readiness check; restores PostgreSQL in an `always` block; then
requires recovered readiness and a redacted resolved recovery request. Its outer cleanup retires
the disposable project and revokes the persona. It does not prove application-specific writes because `http-echo`
does not use its database.

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-postgres-outage.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_postgres_drill_host=platform \
  -e platform_allow_postgres_outage_drill=true \
  -e platform_postgres_outage_acknowledgement=I_ACCEPT_POSTGRES_OUTAGE
```

## Verify component public exposure

Component services are private unless their v1alpha2 declaration sets `exposure: public`.
Only one public service is supported; its hostname is `<component>-<project>.<APPS_DOMAIN>`.
The component acceptance playbook verifies the generated route object. On the protected lab,
after DNS and certificate readiness, make one HTTPS request to that hostname; then deploy a
private revision and confirm the ingress is removed and no application response remains. This
is a manual edge/TLS check because local unit tests and cluster object checks do not prove
public DNS, certificate issuance, or proxy forwarding. Follow ADR-009 before testing a public domain.
The authorized `GET /projects/<project>/resources` response lists each declared HTTPS URL in
`public_endpoints`. Its `tls.state: unknown` deliberately means the platform has not observed
the edge certificate; do not treat it as a readiness signal.

## Approve component outbound connectivity

Outbound traffic is deny-by-default. Set `ALLOWED_EGRESS_CIDRS` (comma-separated CIDRs) and
`ALLOWED_EGRESS_PORTS` (comma-separated TCP ports) in the platform host's `.env`, then restart the Platform API.
Both values must be syntactically valid; an invalid value fails closed. A service component may
request only a CIDR wholly contained in that allow-list and a listed port; the platform rejects all other requests
before deployment and emits a component-scoped NetworkPolicy for approved traffic. Do not use domain names here:
Kubernetes NetworkPolicy enforces IP ranges, not stable DNS identities.

After changing an allow-list, use a disposable workload and a non-production endpoint to prove one approved
connection succeeds and a neighbouring denied IP/port fails. Record the target CIDR, port, policy revision, and
cleanup result. Do not add broad public CIDRs merely to make an application work.

The protected egress acceptance drill is an exception for test execution: it temporarily replaces only
`ALLOWED_EGRESS_CIDRS` and `ALLOWED_EGRESS_PORTS` and disables capacity admission, recreates only
`platform-api`, then restores the exact pre-drill `.env` and API container in its `always` cleanup. It must still run only in an approved protected
environment.

## Configure a project quota

Set `PROJECT_QUOTAS_JSON` in the platform host's `.env` and restart the Platform API. It is a JSON object
whose optional `default` entry applies to every project and whose project-name entries override that default.
Only `pods`, `requests.cpu`, `requests.memory`, `limits.cpu`, and `limits.memory` may be changed; service and
storage restrictions remain managed hardening controls. For example:

```dotenv
PROJECT_QUOTAS_JSON={"default":{"pods":"6","requests.cpu":"1200m","requests.memory":"1536Mi","limits.cpu":"2400m","limits.memory":"3Gi"},"batch":{"pods":"3"}}
```

The API validates a component rollout, including its rolling-update surge, against the same effective quota
that it writes to the namespace. Invalid policy JSON or unsupported values fails closed; fix the operator
configuration rather than retrying a developer request. Inspect the effective safe policy through
`GET /operator/projects/<project>/security-configuration` as a platform administrator. Before raising a quota,
perform the protected capacity exercise below; this local policy does not reserve physical host capacity.

## Inspect platform capacity

Use a short-lived **platform-admin** token to inspect Kubernetes node capacity,
allocatable CPU/memory, and current NodeMetrics usage. This is a cluster-wide
operator surface, not a project endpoint:

```bash
curl --fail-with-body http://127.0.0.1:8000/operator/capacity \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" | jq
```

`state: ok` means the Kubernetes API answered. Each node has `capacity` and
`allocatable`; `usage_state: ok` means metrics-server supplied a current sample,
while `missing` means no sample was returned. `state: unavailable` means the
platform could not query either node inventory or NodeMetrics; it must not be
interpreted as zero usage. The deployed `ansible/test-platform.yml` drill
exercises this endpoint and requires at least one node with capacity,
allocatable values, and a metrics sample.

The platform-admin response also contains `admission`. When request admission is enabled,
it reports aggregate `allocatable`, active-pod `requested`, configured `reserve`, and computed
`available` values using explicit `cpu_millicores` and `memory_mib` units. This is the exact
request accounting used for admission, not live utilization. Disabled, invalid-policy, and
Kubernetes-query states are explicit and never imply free capacity.

This endpoint is deliberately not a host-capacity or storage guarantee. Before
raising project quotas or making a capacity promise, perform a protected,
recorded manual load exercise: collect host CPU/memory/disk, Docker shared
service usage, `kubectl top nodes` and project usage during representative load;
then verify the workload receives an `Unschedulable` diagnostic before its
requested resources exceed the agreed reserve. Confirm alert delivery for the
chosen threshold at the same time. Do not run that exercise against production
data without an approved load plan and rollback conditions.

After that measurement, an operator may enable conservative request admission with
`CAPACITY_ADMISSION_ENABLED=true`, `CAPACITY_RESERVE_CPU_MILLICORES`, and
`CAPACITY_RESERVE_MEMORY_MIB` in `.env`. The API then lists Kubernetes Nodes and active Pods,
subtracts the explicit reserve and current pod requests from allocatable capacity, and rejects a rollout whose
requested resources do not fit. It fails closed with `503` if Kubernetes capacity cannot be read. Keep it disabled
until the reserve is measured; it is a request-based admission guard, not a live-usage or storage guarantee. On a
protected lab, verify one intentionally oversized disposable rollout is rejected with `422`, then confirm a
within-reserve rollout proceeds and remove the disposable workload.

Automate the protected admission check with a disposable project:

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-capacity-admission.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_capacity_drill=true \
  -e platform_capacity_drill_acknowledgement=I_ACCEPT_CAPACITY_DRILL
```

The playbook preserves the exact host `.env`, temporarily enables admission with a valid zero
reserve, and recreates only `platform-api`. It then uses the admission snapshot to create a temporary restricted namespace with a
synthetic Kubernetes pod request. That request leaves less than the drill workload's 100m CPU
or 128Mi memory available, so the API must return the specific aggregate-capacity rejection.
The playbook removes the reservation, waits for request capacity to recover, deploys the real
workload, and retires its project. Both namespaces and the original `.env`/API configuration
are restored in `always` handling. The
synthetic pod may remain Pending and consumes scheduling requests, not representative CPU or
memory load; do not treat this mechanism test as the operator's reserve measurement.
Run it only in an exclusive protected acceptance window: it recreates `platform-api` twice
and temporarily replaces the admission policy, although the original `.env` is retained in
memory and restored byte-for-byte before cleanup continues.

## Run the remaining automated Phase 2C drills

The data-aware rollback drill creates its own project and managed database, inserts a
unique SQL marker, rotates and confirms a write-only secret, rolls the application back,
and verifies the marker and current secret metadata remain. It never reads a secret value:

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-rollback-data.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_rollback_drill_host=platform
```

The egress drill supplies a temporary default target of
[Cloudflare's public DNS-over-TLS listener](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-tls/),
`1.1.1.1:853`. It applies only `1.1.1.1/32` and TCP port `853` during
the test and restores the prior Platform API environment during cleanup:

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-egress-policy.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_egress_drill=true \
  -e platform_egress_drill_acknowledgement=I_ACCEPT_EGRESS_DRILL
```

If that public listener is unavailable from workload pods, override all three target
values together with a reachable listener you control: `platform_egress_target_host`,
`platform_egress_target_cidr`, and `platform_egress_target_port`.

The playbook first proves an undeclared destination is rejected, then deploys a service
whose readiness depends on reaching the approved listener. Do not use the managed
PostgreSQL endpoint: its baseline database exception would not prove the requested
component egress rule.

The identity-provider drill creates its own project, administrator persona and deployment
credential, stops Keycloak, proves local revocation denies an already-issued token while
provider cleanup is pending, restores Keycloak in an `always` block, and observes cleanup:

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-identity-provider-outage.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_identity_drill_host=platform \
  -e platform_allow_identity_outage_drill=true \
  -e platform_identity_outage_acknowledgement=I_ACCEPT_IDENTITY_OUTAGE
```

These playbooks automate in-platform assertions and cleanup. Final acceptance still needs
manual evidence for public DNS/TLS from an external network, actual notification receipt,
and the project-specific backup/retention decision; those properties cannot be established
by a process running inside the same platform failure boundary.

For application, ingress, and local-monitoring failure/recovery assertions, run the guarded
failure-signal drill. It waits through the Prometheus alert `for` durations, so allow roughly
ten minutes:

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-failure-signals.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_failure_drill_host=platform \
  -e platform_allow_failure_signal_drill=true \
  -e platform_failure_drill_acknowledgement=I_ACCEPT_FAILURE_SIGNAL_DRILL
```

The drill temporarily disables capacity admission so its disposable canary cannot be
rejected by an unrelated capacity reservation. It restores the exact platform host
`.env` and recreates `platform-api` during `always` cleanup, in addition to restoring
the proxy and Prometheus.

It creates and retires a public canary, verifies project-labelled application and ingress
alerts, restores both boundaries, and proves Prometheus unavailability and recovery. Use the
existing `operations/heartbeat/ansible/drill-cluster-availability.yml` for the Kubernetes
control plane and `ansible/test-platform-postgres-outage.yml` for the database boundary.
Actual FIRING/RESOLVED delivery and detection while Prometheus itself is unavailable still
require evidence from the independent notification/watchdog systems.

## External heartbeat missing

Check the sender on the platform host:

```bash
sudo systemctl status platform-heartbeat.timer
sudo systemctl status platform-heartbeat.service
sudo journalctl -u platform-heartbeat.service -n 50 --no-pager
```

The oneshot service can be inactive between successful runs; inspect its last result and timer schedule. It sends only when API dependency readiness and Prometheus readiness pass. Check those endpoints first, then sender connectivity, endpoint/token configuration, and TLS without printing secrets.

On the external watchdog host, inspect the hosting scheduler or `crontab -l`, PHP CLI extensions, and cron diagnostics using the [watchdog guide](../../../operations/watchdog/README.md). A stale cron makes the status page unavailable, but has no independent notifier. Under [ADR-011](../../architecture/decisions/ADR-011-watchdog-monitoring-boundary.md), silent watchdog failure is an accepted lab limitation; no additional external observer is required. Manually running cron can send real email; use the documented alert exercise with intended recipients. Verify both the down and recovery notifications. A heartbeat alone does not verify application data or Alertmanager delivery.

## Docker or k3d unavailable

Inspect host disk/memory, Docker logs, and node status before changing resources. PostgreSQL and monitoring are outside k3d and should survive a cluster-only outage. Use the [start/stop procedure](../lifecycle.md#stop-and-restart) after resolving the cause; do not begin by deleting volumes or the cluster. If the cluster must be recreated, retain database volumes and [reapply stored specs](../backup-and-recovery.md#reapply-restored-projects). No reconciler automatically restores workloads.

## PostgreSQL unreachable or slow

Developers can inspect the managed service at `GET /projects/{name}/data-services`
and submit one of the bounded recovery reasons to `POST .../data-services/recovery-requests`.
Platform administrators review requests through `GET /operator/data-service-recovery-requests`
and acknowledge or resolve them with its request-specific `PATCH` endpoint. These calls report
control-plane database presence, not application transaction integrity; use the controlled
database write/read procedure below before resolving an incident.

Use the readiness and service-log commands above. Inspect host disk, connection limits, locks, database permissions, and connectivity from the affected workload. A read-only connection/activity summary is:

```bash
docker compose exec -T postgres psql -X -U postgres -d platform -c \
  'SELECT datname, usename, state, wait_event_type, count(*) FROM pg_stat_activity GROUP BY datname, usename, state, wait_event_type;'
```

Resolve the cause without granting blanket superuser access. Verify application connectivity and write/read behavior afterwards.

## Low disk space or failed backup

```bash
df -h
df -i
docker system df
docker compose logs --tail=100 postgres
```

Attribute growth before removing anything. Never remove unidentified volumes. Follow [backup creation and verification](../backup-and-recovery.md#make-a-current-backup); the former standalone SQL helper has been removed; use the managed backup service, which includes encrypted upload, readback and freshness reporting. If the scheduled backup playbook is deployed, inspect its independent status and notification channel below. A completed dump does not prove recoverability.

## Closure and target capabilities

Record affected resources, commands, results, actual recovery duration, and remaining uncertainty. Verify an application request, database write/read, and relevant recovery notifications.

Per-user audit investigation and the richer portal and CLI workflows remain target procedures in the [software architecture](../../architecture/application-lifecycle.md). They cannot be used as current incident prerequisites.


## Scheduled backup failed or interrupted

If the optional backup automation is deployed, inspect:

```bash
sudo systemctl status platform-backup.service platform-backup.timer --no-pager
sudo journalctl -u platform-backup.service -n 40 --no-pager
sudo cat /var/lib/developer-platform-backup/status.json
sudo systemctl status platform-backup-notify.timer --no-pager
sudo journalctl -u platform-backup-notify.service -n 20 --no-pager
```

A failure after readback can retain a valid `last_verified_snapshot`; notification
failure is recorded separately in `notification.json`. Restore S3/watchdog access,
then use `sudo systemctl start platform-backup-notify.service` to retry delivery.
For a failed capture/upload, resolve the reported stage and restart the backup
service. The host heartbeat cannot clear backup failures.

If `/var/lib/developer-platform-backup/resume.json` remains, exact container IDs
still require restart. Inspect them before replacing/removing containers. The
recovery service retries all recorded services even if one fails:

```bash
sudo systemctl start platform-backup-recover.service
```

Do not run recovery concurrently with capture or remove the process lock. Avoid
`restic unlock` until all restic processes have stopped and a stale repository lock
has been established. Unverified/pending snapshots require investigation; do not
count them as recovery points. See the [backup deployment guide](../../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts)
for service interruption, retention and restore limits.
