# Operations Runbook

Status: current administrator procedures reviewed against source; commands were not run against a live installation for this update. See the [backlog evidence](../04-development/delivery-backlog.md#evidence-conventions) for checks actually performed. Run commands from the repository root on the affected host; an Ansible installation requires a privileged shell in `/opt/developer-platform`.

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

## Provisioning stuck or failed

In a trusted shell with tracing disabled, export a short-lived authorized OIDC access token and list stored projects:

```bash
export PLATFORM_ACCESS_TOKEN='…'
curl --fail-with-body http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN"
docker compose logs --tail=100 platform-api postgres
```

`provisioning` can remain after process termination. Operation `failed` records a provider/authorization failure; operation `succeeded` means resources were applied, not that the workload is healthy. Inspect the operation's separate `readiness` snapshot: `progressing`, `failed`, `not_found`, and `unknown` are not successful health results. Early dependency failures can prevent any status update. Check the dependency commands above and inspect existing Kubernetes resources before retrying after an ambiguous timeout.

For the example project `hello` (substitute the actual project and namespace):

```bash
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get pods,svc,ingress
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello describe pods
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello get events --sort-by=.metadata.creationTimestamp
kubectl --kubeconfig .runtime/admin.kubeconfig -n project-hello logs deployment/hello --tail=100
```

If an operation fails, fix permissions, image, quota, or dependency problems, then repeat PUT with the project's complete intended spec. It returns an operation ID and status URL:

```bash
curl --fail-with-body -i -X PUT http://127.0.0.1:8000/projects/hello \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @examples/project.json
OPERATION_ID=69fb09ef-5136-4c8a-8ec1-c57467192b9a
curl --fail-with-body "http://127.0.0.1:8000/v1/operations/$OPERATION_ID" \
  -H "Authorization: ******"
```

Operation state `succeeded` means Kubernetes resources were applied. Its live `readiness` snapshot reports replica counts, desired/Deployment images, active image references and IDs, and a reason such as `ImagePullBackOff`, `Unschedulable`, or `ProgressDeadlineExceeded`; inspect pod events/logs and HTTP behavior as needed. The worker reclaims an interrupted operation after restart and retries idempotent steps. Use the actual saved spec for an existing application; the sample would replace its image and port. [Recovery](backup-recovery.md#reapply-restored-projects) shows how to retrieve and reapply the stored catalog. PUT preserves existing databases, provided the configuration and database credentials remain compatible. Do not delete a database to repair a failed workload.

## Minimal API deployment demo

Run on the node with a short-lived `PLATFORM_ACCESS_TOKEN` (see [human access and authorization validation](human-access-and-authorization-validation.md)). `scripts/smoke.py` performs the same flow end to end and is the acceptance check:

```bash
OP=$(curl -fsS -X PUT http://127.0.0.1:8000/projects/demo \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"demo","image":"hashicorp/http-echo:1.0.0","port":5678,"probe_profile":"hello-world"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["operation_id"])')
for i in $(seq 1 12); do curl -fsS -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  http://127.0.0.1:8000/v1/operations/$OP | python3 -c 'import json,sys; o=json.load(sys.stdin); r=o["readiness"]; print(o["state"], r["state"], r["reason"])'; sleep 5; done
curl -fsS -H 'Host: demo.apps.<apps-domain>' http://127.0.0.1/
```

Then restart it with `POST /projects/demo/restart`. To remove a demo project, delete its namespace (`kubectl --kubeconfig .runtime/admin.kubeconfig delete namespace project-demo`), then call `POST /projects/demo/retire` with `{"confirm_name":"demo"}` as `project-admin`; the SQL data and catalog entry are retained.

## Day-2 application flow

Run with a short-lived `PLATFORM_ACCESS_TOKEN`; `P=http://127.0.0.1:8000/projects/demo` and `-H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN"` are implied. Each write returns 202 and `rollout_required`; check `activation` on the matching GET before relying on a change. Evidence: EV-30, EV-33 to EV-37 in the [backlog](../04-development/delivery-backlog.md); `scripts/config_drill.py`, `secret_drill.py`, `log_drill.py` and `retirement_drill.py` perform these flows end to end.

| Task | Call | Check |
| --- | --- | --- |
| Inspect state | `GET $P/drift`, `GET $P/revisions` | `in_sync`, current revision |
| Diagnose | `GET $P/logs?tail=100`, `GET $P/resource-usage` | Lines per pod/container; usage `state` is `ok` |
| Change configuration | `PUT $P/configuration` body `{"values": {"MODE": "a"}}` (replaces the set; optional `If-Match: <revision>`) | `GET $P/configuration` shows `activation: active` |
| Set or rotate a secret | `PUT $P/secrets/NAME` body `{"value": "..."}` | `GET $P/secrets` shows `version` and `state: rotating` once the pods are `active` |
| Finish a rotation | `POST $P/secrets/NAME/confirm` after the application works with the new value | 200, previous value revoked |
| Undo a rotation | `POST $P/secrets/NAME/revert` while `rotating` | New version, pods restart |
| Roll back a release | `GET $P/revisions`, inspect `dependencies`, then `POST $P/rollback` body `{"revision": N}` | New operation `succeeded` |
| Retire | `GET $P/retirement-preview`, then `POST $P/retire` with the `scope_token` and `confirm_name` | Repeat the POST until `200 retired`; project grants are removed and deployment credentials enter provider cleanup; database, role and catalog are retained |

Failure responses: 401 no or expired token; 403 missing grant; 404 unknown project or secret; 400 retire confirmation does not match the project name; 409 `revision_conflict`, `scope_changed`, `name_in_use`, `not_adopted`, `no_previous_version` or a retired project; 422 `invalid_spec`, `unsupported_capability`, `invalid_configuration` or `invalid_secret`; 503 dependency unavailable, retry the same request. Secret values are never returned, logged or audited. Secrets are in the backup bundle (ADR-015); previous values are not.

Revision `dependencies` reports `database: retained` and `application_secrets: current_only`. A rollback reapplies
the retained application spec only: it neither reverses PostgreSQL contents/migrations nor restores historic secret
values, because secret values are deliberately excluded from revisions. Restore those dependencies through their
separate controlled procedures before declaring a rollback recovery complete.

For a protected retirement acceptance, `ansible/retire-platform-project.yml` can create and verify a disposable credential probe when invoked with `-e platform_retire_verify_credential_revocation=true`. After retirement it proves the issued token is denied and polls the platform-administrator retirement view until provider cleanup reaches `revoked`. Do not enable this check for a shared CI credential or a non-disposable project. A provider deletion failure leaves the credential in `revocation_pending` for the existing retry worker rather than active; the drill fails after its bounded wait rather than treating that condition as acceptance.

To have the drill create a unique disposable project, deploy a minimal public workload, and retire both workload and project, run:

```bash
ansible-playbook -i ansible/inventory.yml ansible/retire-platform-project.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_retire_create_disposable_project=true \
  -e platform_retire_verify_credential_revocation=true
```

For an existing purpose-created project, omit `platform_retire_create_disposable_project` and supply an exact repeated confirmation:

```bash
ansible-playbook -i ansible/inventory.yml ansible/retire-platform-project.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_retire_project=retirement-drill-1234567890 \
  -e platform_confirm_retire_project=retirement-drill-1234567890 \
  -e platform_retire_verify_credential_revocation=true
```

Before retirement, record the project database/role, the latest **verified** backup snapshot identifier and its
independent restore evidence, and the chosen decision (`retain` or separately approved deletion). The Platform API
does not infer project-level backup coverage from a retained database: the backup bundle is platform-wide and no
project-addressable snapshot index exists. If that evidence is unavailable, retain the data and record the decision
as `backup coverage unverified`; do not perform a destructive database action as part of retirement.

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

## Restart an application

`POST /projects/{name}/restart` (same `change` permission as PUT) queues a rolling restart of the current spec without creating a revision. It returns an operation ID; poll `GET /v1/operations/{id}`, where readiness reports `progressing` until the new pods are ready. Repeating the call while a restart is pending reuses that operation. Only `applied` projects can be restarted.

## Application unhealthy after deployment

Inspect rollout, logs, pod events, image pulls, resource limits, probes, and database connectivity. Compare the desired image/port with your externally retained prior spec and migration records; the platform stores only the latest spec. A manual rollback is another PUT of a known compatible spec, followed by rollout and application verification. It does not roll back database schema changes.

For the default local sample route:

```bash
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

Use the configured HTTPS hostname for public applications. The sample only echoes HTTP; acceptance additionally requires an application-specific PostgreSQL write/read with known test data.

## External heartbeat missing

Check the sender on the platform host:

```bash
sudo systemctl status platform-heartbeat.timer
sudo systemctl status platform-heartbeat.service
sudo journalctl -u platform-heartbeat.service -n 50 --no-pager
```

The oneshot service can be inactive between successful runs; inspect its last result and timer schedule. It sends only when API dependency readiness and Prometheus readiness pass. Check those endpoints first, then sender connectivity, endpoint/token configuration, and TLS without printing secrets.

On the external watchdog host, inspect the hosting scheduler or `crontab -l`, PHP CLI extensions, and cron diagnostics using the [watchdog guide](../../operations/watchdog/README.md). A stale cron makes the status page unavailable, but has no independent notifier. Under [ADR-011](../03-decisions/ADR-011-watchdog-monitoring-boundary.md), silent watchdog failure is an accepted lab limitation; no additional external observer is required. Manually running cron can send real email; use the documented alert exercise with intended recipients. Verify both the down and recovery notifications. A heartbeat alone does not verify application data or Alertmanager delivery.

## Availability drill

For controlled acceptance checks on the existing lab, use the [cluster and Docker-boundary playbooks](../../operations/heartbeat/README.md#availability-drills). They restore the selected service automatically and do not delete cluster or application data. Confirm emails separately before recording acceptance.

## Docker or k3d unavailable

Inspect host disk/memory, Docker logs, and node status before changing resources. PostgreSQL and monitoring are outside k3d and should survive a cluster-only outage. Use the [start/stop procedure](deployment.md#current-installation-and-lifecycle) after resolving the cause; do not begin by deleting volumes or the cluster. If the cluster must be recreated, retain database volumes and [reapply stored specs](backup-recovery.md#reapply-restored-projects). No reconciler automatically restores workloads.

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

Attribute growth before removing anything. Never remove unidentified volumes. Follow [backup creation and verification](backup-recovery.md#make-a-current-backup); the former standalone SQL helper has been removed; use the managed backup service, which includes encrypted upload, readback and freshness reporting. If the scheduled backup playbook is deployed, inspect its independent status and notification channel below. A completed dump does not prove recoverability.

## Compromised credential or access revocation

Revoke a project or platform grant through the authorized API, then verify the affected principal's next request returns `403` and inspect the corresponding redacted audit event. Token expiry/revocation at the identity provider is a separate control; platform authorization does not wait for a token to expire after a grant is removed. The one-time `PLATFORM_BOOTSTRAP_SUBJECT` is host configuration, not an API credential; remove it after first startup.

Preserve `DATABASE_KEY` during recovery. Changing it changes derived Secrets but does not update existing PostgreSQL role passwords; rotation requires coordinated role-password and workload-Secret changes. Follow the [platform configuration notes](../../platform/README.md#configuration). The root [operations notes](../../README.md#operations) describe controller-token rotation. Never include secret values in incident records.

## Closure and target capabilities

Record affected resources, commands, results, actual recovery duration, and remaining uncertainty. Verify an application request, database write/read, and relevant recovery notifications.

Per-user audit investigation and the richer portal and CLI workflows remain target procedures in the [software architecture](../02-architecture/software-architecture.md). They cannot be used as current incident prerequisites.


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
count them as recovery points. See the [backup deployment guide](../../operations/backup/README.md#scheduled-backups-and-independent-backup-alerts)
for service interruption, retention and restore limits.
