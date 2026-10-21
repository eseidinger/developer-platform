# Application runbooks

Status: current administrator procedures reviewed against source.
Run commands from the repository root on the affected host. An Ansible
installation requires a privileged shell in `/opt/developer-platform`.

Use these procedures for application deployment, readiness, and lifecycle incidents. Start with [platform inspection](platform.md#inspect-the-current-installation) when the failure may involve shared services.

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
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN"
```

Operation state `succeeded` means Kubernetes resources were applied. Its live `readiness` snapshot reports replica counts, desired/Deployment images, active image references and IDs, and a reason such as `ImagePullBackOff`, `Unschedulable`, or `ProgressDeadlineExceeded`; inspect pod events/logs and HTTP behavior as needed. The worker reclaims an interrupted operation after restart and retries idempotent steps. Use the actual saved spec for an existing application; the sample would replace its image and port. [Recovery](../backup-and-recovery.md#reapply-restored-projects) shows how to retrieve and reapply the stored catalog. PUT preserves existing databases, provided the configuration and database credentials remain compatible. Do not delete a database to repair a failed workload.

## Minimal API deployment demo

Run on the node with a short-lived `PLATFORM_ACCESS_TOKEN` (see [human access and authorization validation](../validation/access-and-authorization.md)). This deliberately uses the legacy flat declaration and its direct sample route, not the hosted-access contract. `scripts/tests/platform/smoke.py` checks this legacy flow; the [neutral hosted-access harness](../validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness) checks protected `v1alpha2` applications.

```bash
OP=$(curl -fsS -X PUT http://127.0.0.1:8000/projects/demo \
  -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"demo","image":"hashicorp/http-echo:1.0.0","port":5678,"probe_profile":"hello-world"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["operation_id"])')
for i in $(seq 1 12); do curl -fsS -H "Authorization: Bearer $PLATFORM_ACCESS_TOKEN" \
  http://127.0.0.1:8000/v1/operations/$OP | python3 -c 'import json,sys; o=json.load(sys.stdin); r=o["readiness"]; print(o["state"], r["state"], r["reason"])'; sleep 5; done
curl -fsS -H 'Host: demo.apps.<apps-domain>' http://127.0.0.1/
```

Then restart it with `POST /projects/demo/restart`. To retire the disposable demo,
use `GET /projects/demo/retirement-preview` and submit its exact `scope_token`
with `confirm_name: demo` to `POST /projects/demo/retire` as an authorized project
administrator. The platform removes the namespace and queues credential cleanup;
poll until retirement completes. SQL data and the catalog remain retained. Do
not manually delete the namespace as the normal retirement procedure.

## Day-2 application flow

Run with a short-lived `PLATFORM_ACCESS_TOKEN`. Set
`P=http://127.0.0.1:8000/projects/demo` and include the authorization header shown
above. Each write returns 202 and `rollout_required`; check `activation` on the
matching GET before relying on a change. Evidence: EV-30, EV-33 to EV-37 in the
[backlog](../../maintainers/delivery/backlog.md). The scoped
`scripts/tests/platform/check-lifecycle.py` runner consolidates configuration,
secret rotation/revert/confirm, failed-pod log redaction, authorization/audit,
and retirement checks. See the
[script test guide](../../../scripts/tests/README.md) for prerequisites, the
offline plan, and cleanup behavior. Old drill names in historical evidence refer
to their recorded commits.

| Task | Call | Check |
| --- | --- | --- |
| Inspect state | `GET $P/drift`, `GET $P/revisions` | `in_sync`, current revision |
| Diagnose | `GET $P/logs?tail=100`, `GET $P/resource-usage` | Lines per pod/container; usage `state` is `ok` |
| Retained operations | `GET $P/retained-logs?component=api&tail=100` | Bounded JSON messages and operational events, including retired pod instances; view grant required; storage failure is `unavailable` |
| Change configuration | `PUT $P/configuration` body `{"values": {"MODE": "a"}}` (replaces the set; optional `If-Match: <revision>`) | `GET $P/configuration` shows `activation: active` |
| Set or rotate a secret | `PUT $P/secrets/NAME` body `{"value": "..."}` | `GET $P/secrets` shows `version` and `state: rotating` once the pods are `active` |
| Finish a rotation | `POST $P/secrets/NAME/confirm` after the application works with the new value | 200, previous value revoked |
| Undo a rotation | `POST $P/secrets/NAME/revert` while `rotating` | New version, pods restart |
| Roll back a release | `GET $P/revisions`, inspect `dependencies`, then `POST $P/rollback` body `{"revision": N}` | New operation `succeeded` |
| Retire | `GET $P/retirement-preview`, then `POST $P/retire` with the `scope_token` and `confirm_name` | Repeat the POST until `200 retired`; project grants are removed and deployment credentials enter provider cleanup; independent store data and catalog are retained |

Failure responses: 401 no or expired token; 403 missing grant; 404 unknown project or secret; 400 retire confirmation does not match the project name; 409 `revision_conflict`, `scope_changed`, `name_in_use`, `not_adopted`, `no_previous_version` or a retired project; 422 `invalid_spec`, `unsupported_capability`, `invalid_configuration` or `invalid_secret`; 503 dependency unavailable, retry the same request. Secret values are never returned, logged or audited. Secrets are in the backup bundle (ADR-015); previous values are not.

Revision `dependencies` still reports the legacy `database: retained` metadata
and `application_secrets: current_only`; it is not an inventory or health check
for independent named stores. Inspect actual bindings/resources separately. A rollback reapplies
the retained application spec only: it neither reverses PostgreSQL contents/migrations nor restores historic secret
values, because secret values are deliberately excluded from revisions. Restore those dependencies through their
separate controlled procedures before declaring a rollback recovery complete.

For a protected retirement acceptance, `ansible/operations/retire-platform-project.yml` can create and verify a disposable credential probe when invoked with `-e platform_retire_verify_credential_revocation=true`. After retirement it proves the issued token is denied and polls the platform-administrator retirement view until provider cleanup reaches `revoked`. Do not enable this check for a shared CI credential or a non-disposable project. A provider deletion failure leaves the credential in `revocation_pending` for the existing retry worker rather than active; the drill fails after its bounded wait rather than treating that condition as acceptance.

To have the drill create a unique disposable project, deploy a minimal public workload, and retire both workload and project, run:

```bash
ansible-playbook -i ansible/inventory.yml \
ansible/operations/retire-platform-project.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_retire_create_disposable_project=true \
  -e platform_retire_verify_credential_revocation=true
```

For an existing purpose-created project, omit `platform_retire_create_disposable_project` and supply an exact repeated confirmation:

```bash
ansible-playbook -i ansible/inventory.yml \
ansible/operations/retire-platform-project.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_retire_project=retirement-drill-1234567890 \
  -e platform_confirm_retire_project=retirement-drill-1234567890 \
  -e platform_retire_verify_credential_revocation=true
```

Before retirement, record owned resource UUIDs, consumer bindings and credential cleanup state, the latest **verified** backup snapshot identifier and its
independent restore evidence, and the chosen decision (`retain` or separately approved deletion). The Platform API
does not infer project-level backup coverage from a retained database: the backup bundle is platform-wide and no
project-addressable snapshot index exists. If that evidence is unavailable, retain the data and record the decision
as `backup coverage unverified`; do not perform a destructive database action as part of retirement.

Named resource retirement revokes affected access and retains data. Removing a
consumer application/binding leaves shared resources and other consumers intact.
Named-store purge is a separate UUID/owner/version-confirmed action after cleanup;
it waits for verified off-host purge intent. Project-catalog purge never implicitly
drops named resources. See the [named-store lifecycle](../data-stores.md).

## Restart an application

`POST /projects/{name}/restart` (same `change` permission as PUT) queues a rolling restart of the current spec without creating a revision. It returns an operation ID; poll `GET /v1/operations/{id}`, where readiness reports `progressing` until the new pods are ready. Repeating the call while a restart is pending reuses that operation. Only `applied` projects can be restarted.

## Application unhealthy after deployment

Inspect rollout, logs, pod events, image pulls, resource limits, probes, and
database connectivity. The platform retains desired revisions within the
configured revision-retention limit (default 25). Use
`GET /projects/{name}/revisions` and compare retained images, components and
dependency semantics with your application migration records. For an available
compatible revision, use `POST /projects/{name}/rollback` with `{"revision": N}`
and an optional current-revision `If-Match`; poll the returned operation and
verify live readiness and application behavior. Alternatively, apply a complete
known compatible declaration as a new desired revision. Neither path rolls back
database contents/migrations or restores historical secret values.

For the legacy flat local sample route only:

```bash
curl --fail-with-body -H 'Host: hello.apps.localhost' http://127.0.0.1/
```

Use the configured HTTPS hostname for public applications. The legacy sample
only echoes HTTP; acceptance additionally requires an application-specific
PostgreSQL write/read with known test data. Protected `v1alpha2` routes need the
hosted policy and approvals below; the legacy route is not evidence of hosted
authentication or authorization.

## Public access denied while the workload is ready

For `v1alpha2`, public ingress traverses the authorizer and the backend accepts
only authorizer traffic. First inspect
`GET /v1/projects/{project}/applications/{application}/access-policy` and its
operation as an authorized project administrator. Missing/pending/inactive policy
denies public access; workload readiness does not prove policy activation.

Check the exact path/method and authentication mode. A browser route redirects
to login and first login can return pending `403` until a provider administrator
approves groups. A bearer route returns `401` for missing/invalid/expired or
wrong-audience tokens, and `403` for unapproved principals, missing groups or
unmatched routes. Invalid path encoding returns `400`; an expired authorization
snapshot or unavailable boundary dependency can return `503`. Platform roles and
deployment credentials grant no implicit application membership. For browser
writes, verify the same HTTPS Origin and platform CSRF cookie/header.

Use the [hosted API guide](../../developers/api.md#hosted-application-access),
[installation runbook](../identity-and-access.md#hosted-application-access-installation-and-recovery),
and [security runbook](security.md#hosted-application-revocation-and-rotation).
Do not bypass the authorizer, forge principal headers, expose the backend, or
widen NetworkPolicies to make a denied request work.

## Availability drill

For controlled acceptance checks on the existing lab, use the [cluster and Docker-boundary playbooks](../../../operations/heartbeat/README.md#availability-drills). They restore the selected service automatically and do not delete cluster or application data. Confirm emails separately before recording acceptance.
