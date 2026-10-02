# Phase 1B access-validation runbook

Use this controlled lab procedure to gather evidence for individual OIDC access,
platform-owned project grants, immediate grant revocation, and durable audit
writes. It supports the Phase 1B acceptance work for OPS-004-T01 and part of
OPS-001-T01; it does not close either task on its own.

Run from the repository root. Use disposable project names and separate human
accounts. Do not put access tokens, Keycloak passwords, user-subject lists, or
audit-reader credentials in Git, `.env`, shell history, or evidence output.

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
- [ ] Obtain separate viewer/developer/project-admin tokens and execute the
  role-denial/cross-project matrix.
- [ ] Grant, revoke, and prove immediate denial for a second platform-admin
  token; correlate the request outcomes with durable audit records.
- [ ] Complete restricted audit inspection/export, backup coverage, security
  alert delivery/grouping, and all remaining OPS-001/002/004 acceptance work.

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
