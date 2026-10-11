# Human access and authorization validation

Status: current validation procedure with dated evidence called out separately.

Use this controlled lab procedure to gather evidence for individual OIDC access,
platform-owned project grants, immediate grant revocation, and durable audit
writes. It supports the Phase 1B acceptance work for OPS-004-T01 and part of
OPS-001-T01; it does not close either task on its own.

Run from the repository root. Use disposable project names and separate human
accounts. Do not put access tokens, Keycloak passwords, user-subject lists, or
audit-reader credentials in Git, `.env`, shell history, or evidence output.

The [access-validation portal](../../../platform/README.md#access-validation-portal)
offers the same API actions through browser PKCE login after Keycloak bootstrap.
It is useful for the project/grant/revocation and restricted-inspection portions
of this runbook; create the separate Keycloak test users first and retain only
redacted HTTP results as evidence.

## Neutral hosted-application acceptance harness

Source status (October 11, 2026): the harness is implemented and tested locally;
the deployed hosted-access gate has **not** been executed or closed. Run it only
after the [hosted-access installation](../identity-and-access.md#hosted-application-access-installation-and-recovery)
is deployed. It does not deploy, upgrade, or reset the platform.

The entry point is `scripts/check-hosted-access.py`. It uses two uniquely named
projects, `ha-<12-hex-run-id>-provider` and `ha-<run-id>-consumer`, each with one
public API, one private worker, and its own PostgreSQL database. The neutral
fixture deliberately has no application authorization and contains only synthetic
markers. Never use its image with real application data.

### Prepare the runner and fixture

Create a runner environment on the platform host (Python 3.12 or newer):

```bash
python3 -m venv .runtime/acceptance-venv
.runtime/acceptance-venv/bin/pip install -r platform/acceptance/requirements.txt
docker build -f platform/acceptance/Dockerfile.fixture \
  -t <your-public-registry>/hosted-access-fixture:<version> platform/acceptance
```

Publishing is a separate operator action, not part of the harness. Publish the
fixture to an approved **public** registry and obtain its immutable registry
digest. Supply `<registry>/hosted-access-fixture@sha256:<64-hex-digest>` below;
a local image ID or a mutable tag is insufficient. The fixture is non-root and
works with a read-only root filesystem.

Before a live run, wildcard application DNS, public HTTPS certificates trusted
by the host and fixture container, the hosted authorizer/proxy, the provisioner's
existing client/user-management permissions, and available workload capacity
must be ready. Approve the provider and issuer's apply-time IP addresses on TCP
443 through the normal operator egress configuration. The harness neither
widens that allow-list nor disables TLS checks. Supply a resolvable unrelated
host outside those permitted addresses for the negative egress assertion.
The operator needs access to the host's private `.env`, `kubectl`, and
`.runtime/admin.kubeconfig`. Override `--kubectl` or `--settings` if necessary.

Use the Device Authorization/PKCE procedure below to authenticate an existing
**human platform administrator**. Save its token response privately as a mode
`0600` JSON session file containing exactly `access_token`, `refresh_token`, and
`client_id` (normally `platform-cli`). Do not supply passwords, bearer tokens,
refresh tokens, or client secrets as command arguments. The harness renews the
operator session in memory; it never writes renewed credentials to the journal.
Obtain a fresh session for crash recovery if the original session is no longer
usable. The existing operator account and its grants are not changed.

### Plan, execute, and clean up

An offline plan performs no network calls or writes:

```bash
.runtime/acceptance-venv/bin/python scripts/check-hosted-access.py plan \
  --run-id 0123456789ab \
  --fixture-image '<public-registry>/hosted-access-fixture@sha256:<digest>' \
  --apps-domain apps.example.org \
  --issuer https://identity.example.org/realms/platform
```

Choose a fresh run ID for each live run. Repeat the API origin exactly as the
explicit environment confirmation:

```bash
.runtime/acceptance-venv/bin/python scripts/check-hosted-access.py run \
  --api http://127.0.0.1:8000 \
  --confirm-environment http://127.0.0.1:8000 \
  --run-id 0123456789ab \
  --fixture-image '<public-registry>/hosted-access-fixture@sha256:<digest>' \
  --apps-domain apps.example.org \
  --operator-token-file .runtime/operator-session.json \
  --unrelated-host example.com
```

The core run verifies digest-pinned ready deployments; synthetic classification
and retention records; pending human first login, explicit provider approval,
group headers, bounded claim refresh, cookie/CSRF handling and stable identity;
provider-approved service credentials and client-scoped groups/audience; allowed
public HTTPS consumer-to-provider traffic and hashed synthetic correlation;
project-wide credential visibility in the private worker; missing/invalid/wrong-audience,
unapproved/wrong-group, ambiguous/unmatched path and forged-header denials;
private-backend bypass and unrelated-egress denial; retained, project-isolated
PostgreSQL state after restart; policy activation/rollback; normal and emergency
rotation; and denial of already issued tokens/sessions after revocation.
DNS/network errors do not count as a successful isolation check.

`--timed` additionally holds a real machine token until expiry (up to five
minutes). `--allow-recovery-reconcile` separately authorizes the **global**
catalog-to-identity-provider reconciliation endpoint, so it requires an isolated
lab with no other project records, including retired records. It verifies stable
principals and state, invalidated browser sessions and old machine credentials,
and replacement credentials. This is a reconciliation rehearsal, **not** a
backup restore, and it cannot establish backup/recovery acceptance. Do not use
the flag on a shared lab; the inventory check cannot prevent concurrent creation
of another project, so reserve the lab for the duration of the drill.

Normal completion and caught failures attempt fixture retirement and synthetic
identity cleanup. The harness refuses changed or out-of-scope resources. It
never purges databases: retained fixture databases require a separate operator
decision. It creates a temporary synthetic human administrator solely to prove
that platform administration gives no implicit application membership; cleanup
removes that grant and account. Abrupt termination or unavailable dependencies
can leave resources or cleanup pending. Keep the private journal and retry:

```bash
.runtime/acceptance-venv/bin/python scripts/check-hosted-access.py cleanup \
  --api http://127.0.0.1:8000 \
  --confirm-environment http://127.0.0.1:8000 \
  --run-id 0123456789ab \
  --operator-token-file .runtime/operator-session.json
```

The default output directory is `.runtime/hosted-access/<run-id>` (mode `0700`).
Its `state.json` contains cleanup handles but no credentials. Its mode-`0600`
`report.json` contains named assertions, safe timings/statuses, fixture image,
deployment revisions/operation IDs, resource bounds, harness source hash,
synthetic project/route references, and pinned egress
CIDRs; it contains no raw identity claims, cookies, passwords, tokens, or secret
values. Treat the evidence as Internal. For `run`, exit zero means the selected core checks
and cleanup completed; `result: core-passed` always has `gateClosed: false`.
Exit nonzero means a failed check, dependency/configuration problem, or incomplete
cleanup. Review the report before using it as evidence.

The full gate still needs the explicit deferred checks: a verified backup
restore, control-plane outage/five-minute fail-closed behavior, long browser and
rotation timers, request retention, component monitoring/centralized log
retention, DNS-address-change/reapply behavior, and the separately owned versioned energy-system suite. Skipped
optional drills are also recorded as deferred, never as passed.

For remote execution, `ansible/test-platform-hosted-access.yml` defaults to
`plan` and uses the prepared runner environment above. Supply
`hosted_access_run_id`, `hosted_access_fixture_image`, and
`hosted_access_apps_domain`, plus `hosted_access_issuer` for the offline plan;
for `run` or `cleanup`, additionally supply
`hosted_access_command`, `hosted_access_confirm_environment` equal to
`hosted_access_api`, and the **target-host path**
`hosted_access_operator_token_file`. Optional flags are
`hosted_access_timed` and `hosted_access_allow_recovery_reconcile`, both false
by default. It does not transfer credentials or install dependencies.

Local verification: the offline/safety/fixture tests pass, the fixture image
builds, and its non-root/read-only readiness and real PostgreSQL persistence
checks pass against disposable containers. These checks do not contact the
running platform or substitute for the live acceptance run.

## Executed local validation — October 2, 2026

The following controlled checks completed on the local lab. They are local
verification evidence, not Phase 1B task closure; the remaining checks below
are still required.

- [x] Fresh Keycloak/PostgreSQL bootstrap completed with a new individual
  Keycloak user receiving the one-time persisted `platform-admin` grant.
- [x] `platform-cli` Device Authorization with PKCE issued a short-lived OIDC
  token for that administrator, and `GET /projects` succeeded.
- [x] The audit boundary was repaired and deployed: a controlled append through
  the restricted writer succeeded, while a direct writer `INSERT` was denied.
- [x] Disposable authorization project A exists and received separate `viewer`,
  `developer`, and `project-admin` grants.
- [x] The browser PKCE portal completed Keycloak login for the deployed
  identity provider without retaining an access token outside the browser tab.
- [x] Separate viewer/developer/project-admin users completed the
  role-denial/cross-project matrix.
- [x] A second platform-admin grant was revoked; its unchanged token received
  `403` on the next request and the outcomes were correlated with audit records.
- [x] A platform administrator completed restricted inspection/export and a
  developer was denied operator access; audit export was redacted.
- [x] The SMTP synthetic delivery test succeeded and controlled authentication,
  authorization-denial, and privileged-change events fired their security rules.
- [x] Real security-rule notifications were received and repeated events stayed
  one grouped ongoing incident. Retained evidence is not required for these
  owner-confirmed checks.
- [x] The controlled notification-delivery-failure exercise is omitted from
  this Phase 1B task by owner direction.

## Bootstrap a fresh local identity service

For a clean local reset, first preserve any required backup and then run:

```bash
bash scripts/down.sh --volumes
python3 scripts/init.py
docker compose up -d postgres keycloak-db-init keycloak proxy
```

`--volumes` deletes PostgreSQL, Keycloak, monitoring, and other Compose service
data as well as the k3d cluster. It preserves `.env`, backups, and installed
tools. A newly generated `.env` has fresh secrets. Do not combine it with an
old PostgreSQL volume: the Keycloak database password will not match.

Open `https://identity.localhost`, choose **Administration Console**, and sign
in as `admin` using `KEYCLOAK_ADMIN_PASSWORD` from `.env`. In the `platform`
realm, create an enabled individual bootstrap user, set a password, and copy
its immutable **ID**. Set that value as `PLATFORM_BOOTSTRAP_SUBJECT` in `.env`,
then start the platform:

```bash
bash scripts/up.sh
```

After the API starts successfully, remove `PLATFORM_BOOTSTRAP_SUBJECT` from
`.env`. The API has persisted the one-time `platform-admin` grant. Verify the
platform before continuing:

```bash
curl --fail-with-body http://127.0.0.1:8000/healthz
curl --fail-with-body http://127.0.0.1:8000/readyz
docker compose ps
```

## Obtain an access token with Device Authorization and PKCE

The public `platform-cli` client disables password grants and requires PKCE,
including for Device Authorization. Caddy uses a local development CA; if the
host `curl` does not trust it, use its root certificate only for this local lab:

```bash
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt \
  .runtime/caddy-local-root.crt
export CURL_CA_BUNDLE="$PWD/.runtime/caddy-local-root.crt"
export ISSUER='https://identity.localhost/realms/platform'
```

Generate a verifier/challenge and request a device code:

```bash
export CODE_VERIFIER="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
export CODE_CHALLENGE="$(printf %s "$CODE_VERIFIER" | python3 -c 'import sys,hashlib,base64; print(base64.urlsafe_b64encode(hashlib.sha256(sys.stdin.buffer.read()).digest()).rstrip(b"=").decode())')"
DEVICE_RESPONSE="$(curl --fail-with-body -sS -X POST "$ISSUER/protocol/openid-connect/auth/device" \
  --data-urlencode 'client_id=platform-cli' \
  --data-urlencode 'scope=openid' \
  --data-urlencode "code_challenge=$CODE_CHALLENGE" \
  --data-urlencode 'code_challenge_method=S256')"
export DEVICE_CODE="$(printf '%s' "$DEVICE_RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["device_code"])')"
printf '%s' "$DEVICE_RESPONSE" | python3 -c 'import json,sys; r=json.load(sys.stdin); print("Open:", r["verification_uri_complete"]); print("Code:", r["user_code"])'
```

Open the printed URL, authenticate as the intended individual user in the
`platform` realm, and approve the request. Only then exchange the device code:

```bash
TOKEN_RESPONSE="$(curl --fail-with-body -sS -X POST "$ISSUER/protocol/openid-connect/token" \
  --data-urlencode 'grant_type=urn:ietf:params:oauth:grant-type:device_code' \
  --data-urlencode 'client_id=platform-cli' \
  --data-urlencode "device_code=$DEVICE_CODE" \
  --data-urlencode "code_verifier=$CODE_VERIFIER")"
export PLATFORM_ACCESS_TOKEN="$(printf '%s' "$TOKEN_RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
unset DEVICE_RESPONSE DEVICE_CODE TOKEN_RESPONSE CODE_CHALLENGE CODE_VERIFIER
```

An `authorization_pending` response means approval has not completed. Tokens
are short-lived; keep them only in the current shell. Reuse this procedure for
every test user and save the resulting tokens under distinct shell variables.

## Create accounts, projects, and scoped grants

In Keycloak, create distinct enabled `platform`-realm users for `viewer`,
`developer`, `project-admin`, and a disposable second `platform-admin` test.
Record their immutable IDs privately. If a local subject file has CRLF endings,
strip carriage returns from values before sending them as JSON.

Keep the bootstrap administrator token separately and create two disposable
projects:

```bash
export ADMIN_TOKEN="$PLATFORM_ACCESS_TOKEN"
export API='http://127.0.0.1:8000'
export A='phase1b-authz-a'
export B='phase1b-authz-b'

for project in "$A" "$B"; do
  curl --fail-with-body -X PUT "$API/projects/$project" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    --data "{\"name\":\"$project\",\"image\":\"hashicorp/http-echo:1.0.0\",\"port\":5678}"
done
```

Grant the three project-scoped roles on project A. Substitute private subject
values; never commit them:

```bash
export VIEWER_SUB='…'
export DEVELOPER_SUB='…'
export PROJECT_ADMIN_SUB='…'

for grant in "$VIEWER_SUB viewer" "$DEVELOPER_SUB developer" "$PROJECT_ADMIN_SUB project-admin"; do
  set -- $grant
  curl --fail-with-body -X PUT "$API/projects/$A/grants" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    --data "{\"issuer\":\"$ISSUER\",\"subject\":\"$1\",\"role\":\"$2\"}"
done
```

A `503` stating that an operation requires an audit record means do not claim
the operation succeeded. Inspect current projects, repair the audit path, and
repeat the same PUT; project provisioning is idempotent.

## Execute and record the permission matrix

Obtain a separate token for each person and store it as `VIEWER_TOKEN`,
`DEVELOPER_TOKEN`, `PROJECT_ADMIN_TOKEN`, and `TEST_PLATFORM_ADMIN_TOKEN`.
Record timestamp, code revision, principal, target project, HTTP status, and
redacted response for every assertion.

| Principal | Expected result |
| --- | --- |
| Viewer on A | Lists A; `PUT /projects/A`, retirement, and grant changes return `403` |
| Developer on A | Lists A and may reapply A's complete spec; retirement and grant changes return `403` |
| Project admin on A | May manage grants on A; mutation and grant changes on B return `403` |
| Platform admin | May access both projects and manage platform grants |

Use the actual project variables. A non-mutating grant attempt is useful for
negative assertions:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X PUT "$API/projects/$A/grants" \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data "{\"issuer\":\"$ISSUER\",\"subject\":\"$VIEWER_SUB\",\"role\":\"viewer\"}"
```

The expected result is `403`. Later Phase 1B data surfaces (logs, metrics,
secrets, and jobs) must receive the same checks when their endpoints exist;
they are not present in the current API.

## Prove immediate platform-grant revocation

Grant the disposable test user platform-admin, verify a project-grant request
succeeds with its still-valid token, revoke that platform grant using the
bootstrap administrator, then repeat the identical project-grant request. The
second request must return `403` without waiting for token expiry. Ensure the
test user has no separate grant on project A.

```bash
export TEST_PLATFORM_ADMIN_SUB='…'
curl --fail-with-body -X PUT "$API/platform/grants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data "{\"issuer\":\"$ISSUER\",\"subject\":\"$TEST_PLATFORM_ADMIN_SUB\",\"role\":\"platform-admin\"}"

curl --fail-with-body -X DELETE "$API/platform/grants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data "{\"issuer\":\"$ISSUER\",\"subject\":\"$TEST_PLATFORM_ADMIN_SUB\"}"
```

Preserve the successful and denied request evidence, then inspect the
corresponding redacted audit events through the restricted operator procedure.
Time-filtered audit inspection/export, deployed backup coverage, security-alert
delivery evidence, and the remaining OPS-001/002/004 acceptance criteria are
separate required work; do not mark Phase 1B complete from this runbook alone.

## Automate restricted inspection and export checks

The non-mutating check below verifies the platform-admin inspection surfaces,
the bounded audit export's redaction, and, when supplied, developer denial. It
prints only pass/fail assertions; it never prints tokens, response bodies, or
audit identities. Run it with the disposable project and short-lived tokens
already obtained above:

```bash
export PLATFORM_ADMIN_TOKEN="$ADMIN_TOKEN"
export PHASE1B_PROJECT="$A"
export DEVELOPER_TOKEN='…' # optional; enables the 403 assertions
.venv/bin/python scripts/check-phase-1b-security.py
```

The API allows only platform administrators to use `/operator/*`. The inspection
result reports the managed workload security and network-policy contract and
secret references by name; it never returns secret values. Audit export requires
an offset-bearing UTC time window no longer than 31 days and is capped at 10,000
events. Use the JSON export for controlled evidence or `format=csv` for a
redacted operator export.

## Test security-event notifications

Complete this exercise only after the SMTP destination has been configured using
the [Alertmanager guide](../../../operations/alertmanager/README.md). It supplies
controlled evidence for OPS-002-T01. Use disposable identities/projects and do
not copy tokens, Keycloak passwords, raw audit details, or Alertmanager
configuration into evidence.

### Preflight the audit collector

The API writes the security-event metric file every 30 seconds through its
restricted audit-reader role. On the deployed host, confirm that the file has a
fresh collection timestamp before generating events:

```bash
cd /opt/developer-platform
docker compose exec -T node-exporter sh -ec \
  'grep platform_security_audit_collection_success /discovery/security-events.prom'
```

If this file is absent or the `SecurityAuditCollectionStale` alert is firing,
repair the collector before continuing. The alert rules cannot prove event
delivery without a fresh metric source.

### Verify the notification destination

Use the synthetic mail exercise from the Alertmanager guide first. It proves
SMTP delivery but not the Prometheus security rules:

```bash
docker compose exec -T alertmanager amtool \
  --alertmanager.url=http://127.0.0.1:9093 alert add \
  alertname=PlatformEmailTest job=manual severity=info \
  --annotation='summary="Operator-requested SMTP delivery test"' \
  --end="$(date -u -d '+2 minutes' +%Y-%m-%dT%H:%M:%SZ)"
```

Record receipt of the FIRING and RESOLVED messages. The normal group wait is 30
seconds; the resolved message follows expiration and the configured group
interval.

### Generate and verify the security rules

The repeated-failure rules require five matching events in the 15-minute window
and remain pending for two minutes. Allow one collector cycle and one Prometheus
scrape before that hold period. Alertmanager groups by alert name and stable
resource labels, so further matching events should remain one ongoing incident.

1. Generate five authentication failures against the same API target:

   ```bash
   for n in $(seq 1 5); do
     curl -sS -o /dev/null -w '%{http_code}\n' \
       https://platform.example.com/projects
   done
   ```

   Substitute the configured platform domain. Each response must be `401`.

2. Sign in as a disposable viewer through the portal, then attempt an
   unauthorized project-grant change on the same project five times. Each result
   must be `403`; this generates `RepeatedAccessDenials` without modifying a
   grant.

3. As a platform administrator, grant or revoke a disposable project role. This
   creates a `PrivilegedChange` event without the repeated-event threshold.

4. Inspect active rule state from the host:

   ```bash
   curl -sS http://127.0.0.1:9090/api/v1/alerts
   ```

   Confirm `RepeatedAuthenticationFailures`, `RepeatedAccessDenials`, and
   `PrivilegedChange` contain the expected severity and resource labels. Confirm
   their notifications arrive and that the repeated activity produces one
   grouped ongoing incident rather than duplicate notifications.

5. Use the portal's restricted audit export for the exact exercise time window.
   Correlate each alert's resource labels and latest event ID with redacted audit
   records. Do not retain raw principal IDs or credentials.

The repeated-event alerts clear after their 15-minute event window no longer
contains five events, plus rule evaluation. Document that delayed resolution;
do not repeatedly generate denials solely to make the alert persist.
