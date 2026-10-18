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

## Human PostgreSQL access acceptance playbook

The opt-in [`test-platform-human-database-access.yml`](../../../ansible/test-platform-human-database-access.yml)
wrapper automates the Phase 10.7 core tunnel and SQL checks. It does **not**
deploy the platform, install the bastion, publish the neutral fixture, or close
the full acceptance gate. Its default `plan` validates the run scope without
contacting the platform API. A live `run` creates two private, run-scoped fixture
projects (`hd-<run-id>-a` and `hd-<run-id>-b`) with separate named resources
and explicit read-write component bindings.
Their data and projects are retained for explicit owner-reviewed retirement;
the runner revokes its temporary human grant and test persona. Never run it
against real application data.

The current runner uses expiring named-resource credentials. Its SQL check expects
the resource's effective `_reader` role: the issued `credential_*` login switches
to that role by its operator-configured database default. Use the lease's `PGUSER`
for authentication. The current full live wrapper rerun remains separate from
EV-52–72's scoped native/browser evidence. Use a dedicated
human administrator with no existing named-store grants or registered SSH key;
it refuses to replace an operator's existing key or disrupt their leases. Historical
evidence below describes the earlier implicit project-database model and does not
establish acceptance for this replacement. See the [current workflow](../data-stores.md).

First deploy the platform and the restricted bastion using
[`install-human-database-access.yml`](../../../ansible/install-human-database-access.yml).
Install or update the host-side runner environment from
`platform/acceptance/requirements.txt` as in [Prepare the runner and fixture](#prepare-the-runner-and-fixture).
Transfer `scripts/check-human-database-access.py`,
`platform/acceptance/human_database.py`, and updated requirements to the target
through the same reviewed runner-only update process used for hosted access;
the Ansible acceptance wrapper does not transfer code. Publish the neutral
fixture to an approved public registry and use its immutable digest, not a tag.

Prepare a mode `0600` renewable human platform-administrator session file on
the target with the [operator-session procedure](#obtain-a-private-operator-session-for-the-hosted-access-harness).
Independently verify the dedicated bastion's Ed25519 host key and place its
`[127.0.0.1]:2222` entry in a root-readable mode `0600` known-hosts file on
the target. Do not generate the trust file from an unverified first connection.
For a non-default private bastion address or port, use the matching host/port
variables; keep the bastion behind the approved management firewall. The
runner requires local root access to verify the installed `sshd` restrictions.

From the controller checkout, use a fresh 12-character lowercase hexadecimal
run ID and the exact API origin (normally the host-local loopback API):

```bash
ansible-playbook -i ansible/inventory.yml ansible/test-platform-human-database-access.yml \
  -e human_database_run_id=0123456789ab \
  -e human_database_fixture_image=docker.io/example/neutral-fixture@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

ansible-playbook -i ansible/inventory.yml ansible/test-platform-human-database-access.yml \
  -e human_database_command=run \
  -e human_database_run_id=0123456789ab \
  -e human_database_fixture_image=docker.io/example/neutral-fixture@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  -e human_database_operator_token_file=/opt/developer-platform/.runtime/operator-session.json \
  -e human_database_known_hosts_file=/opt/developer-platform/.runtime/db-known-hosts \
  -e human_database_confirm_environment=http://127.0.0.1:8000
```

Replace the example digest and run ID; reuse an ID only for inspecting its
report, never for another run. The wrapper hides invocation output because
Ansible log output is not a secret store. The root-only report is at
`/opt/developer-platform/.runtime/human-database-access/<run-id>/report.json`.
It records check names and safe results, no SQL password, SSH private key, or
test-persona secret. Review it privately and record the deployed API/bastion
revisions, fixture digest, and any failed check in the Phase 10.7 evidence.
`core-passed` means only the automated subset passed. Browser storage, remote
firewall reachability, and log/screenshot/evidence redaction still need manual
review. A failed run may leave its projects or a pending test-persona revoke;
inspect the report and the run-scoped API records, retry cleanup through the
documented operator API, and retire/purge only the verified fixture projects
under the normal project-retirement procedure. Do not delete their databases
directly.

## Executed human PostgreSQL access acceptance: October 15, 2026

**EV-47 · owner-accepted passing core tests; partial Phase 10.7 / PLAN-008 evidence.** The live run on
`node-01.eseidinger.de` used two disposable projects,
`hd-5f39d4862423-a` and `hd-5f39d4862423-b`, and the immutable fixture
`docker.io/eseidinger/developer-platform-acceptance-fixture@sha256:5c14c1bedfc653e98f958b88deacc5af488f885a5d9a6d3b96e9325938b3f0ad`.
The private report is
`/opt/developer-platform/.runtime/human-database-access/5f39d4862423/report.json`
(mode `0600`). Run `5f39d4862423` lasted from 17:43:50 to 17:44:13 UTC.
It returned `core-passed`: all 14 named checks passed, cleanup was `complete`,
and `gateClosed` was `false`. The runner revoked its temporary grant and test
persona; it retained both fixture projects for owner-reviewed retirement.

The automated checks covered isolated bastion configuration, a human platform
administrator, two ready project databases, denial of an ungranted key and an
automation grant, a human grant with a distinct SQL credential, an authorized
tunnel, read-only access to the granted database, denial of the foreign project,
termination of an existing SQL session, denial of a new SQL login and SSH key
after revocation, redacted audit events, and test-persona revocation. The
installed bastion was active and listening on `127.0.0.1:2222`; its dedicated
Ed25519 host key was checked against the controller's trusted host key.

The owner then confirmed the browser and SQL journey using a separate portal
grant on project A. The portal displayed a one-time SQL password that
disappeared when its dialog reopened. A tunnel through the operator's
ProxyJump reached the project A database and read its synthetic marker; a write
and a project B login were denied. Replacing the SSH key changed the portal
fingerprint; a new connection with the old key was denied and the replacement
key connected before revocation. After the portal grant was revoked, the owner
observed termination of the existing SQL session and denial of a new SQL login;
a new SSH connection with the replacement key was also denied. After a browser
refresh, the portal showed the grant as revoked and removed the personal
database-identity panel.

Two UI defects surfaced during this journey and were fixed and deployed before
the final portal check: revoke sent surplus grant fields to a strict API and
returned 422, and the personal identity panel displayed stale cached data
after the API returned 404. Focused UI regression tests passed (nine tests
after the second fix), as did UI typecheck, lint, and build. The final deployed
UI asset was `index-C2zxuYLg.js`; the API was ready and the bastion active.
The installation record identified source `b3acaef1e413e698d772c218dc336da8d55684b0+dirty`:
the deployed fixes came from a working tree, so this string does not attest an
exact committed source tree.

**Follow-up, October 15, 2026:** A fresh deployment recorded clean source
revision `9826de70829b47f18b8c8018c9348fc81dcb8c43` at 19:14:21 UTC;
the API `/readyz` returned `ready`. The owner completed retirement of both
fixture projects. A read-only catalog check confirmed both statuses are
`retired`, and PostgreSQL still contains their two retained databases. Project
B first returned `202 retiring` while its namespace was being deleted; after
the namespace disappeared, the confirmed request completed retirement. The
automated and manual access checks above preceded this clean deployment and
were not repeated against it.

**Owner acceptance, October 15, 2026:** The owner accepts the 14 passing
automated checks and the completed manual portal, tunnel, SQL, key-rotation,
and revocation checks as passed evidence. No repeat run is required solely
because the same fixes were subsequently deployed from clean commit `9826de7`.
This decision accepts the checks performed; it does not report the deferred
reviews as passed or change the original report's `gateClosed: false` result.

The external-path probe from the controller could not connect to bastion port
2222, consistent with its loopback listener, but a full remote firewall review
remains deferred. Browser storage and independent log, screenshot, and evidence
redaction review remain deferred too. The retired fixture databases remain
retained under the normal data-retention policy. This record does not close PLAN-008 or the
Phase 10 gate; the three remaining reviews are the final, lowest-priority
[10.8 work package](../../maintainers/delivery/plans/phase-10-anytime-leftovers.md#108-complete-the-lowest-priority-human-database-leftovers-plan-008).
See [EV-47](../../maintainers/delivery/backlog.md#verification-register).

## Neutral hosted-application acceptance harness

Validation status (October 11, 2026): the deployed neutral-fixture core suite,
including held-token expiry, passed in run `c927adee1d50` ([EV-45](../../maintainers/delivery/backlog.md#verification-register)).
The [dated evidence below](#executed-hosted-access-core-acceptance-october-11-2026)
records its scope and remaining checks; the full hosted-access gate is still open. Run it only
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

#### Publish the fixture through GitHub Actions

The [hosted-access fixture workflow](../../../.github/workflows/hosted-access-fixture.yaml)
publishes the neutral fixture, not the host-side runner. It runs harness safety
and real PostgreSQL persistence tests, then checks the amd64 container's readiness
with a non-root user, read-only filesystem, and dropped capabilities. A successful
tag release builds `linux/amd64` and `linux/arm64` images following
[Docker's multi-platform publishing pattern](https://docs.docker.com/build/ci/github-actions/multi-platform/).
It does not deploy the platform, execute live acceptance, or close the gate.

Configure these GitHub repository or `dockerhub` environment settings first:

- Variable `DOCKERHUB_USERNAME`: the Docker Hub account used for login (for example `eseidinger`).
- Optional variable `DOCKERHUB_NAMESPACE`: the destination organization; defaults to the login account.
- Secret `DOCKERHUB_TOKEN`: a Docker Hub access token authorized to push to the destination repository.

Create a **public** Docker Hub repository named
`<namespace>/developer-platform-acceptance-fixture`. Configure the GitHub
`dockerhub` environment with tag restrictions or required reviewers if desired.
Do not store the Docker Hub token in inventory, `.env`, Git, or command arguments.

After committing and pushing the workflow and fixture changes, publish a new
stable version from the intended commit:

```bash
git tag -a hosted-access-v0.1.0 -m "Release neutral hosted-access fixture 0.1.0"
git push origin hosted-access-v0.1.0
```

Only `hosted-access-vMAJOR.MINOR.PATCH` release tags publish images; CLI tags,
branch pushes, and pull requests do not publish. Use a new version for each
release; never move or reuse release tags. The example produces
`docker.io/eseidinger/developer-platform-acceptance-fixture:0.1.0` when the
namespace is `eseidinger`. No mutable `latest` alias is published.

The workflow verifies anonymous registry access and puts the digest-pinned
`export HA_IMAGE=docker.io/<namespace>/developer-platform-acceptance-fixture@sha256:<digest>`
command in its run summary. Copy that reference into the host's shell and use
`--fixture-image "$HA_IMAGE"` for the plan and run below. No Docker Hub login
or local fixture build is needed on the platform host for this published image.

Fixture source changes require publishing a new version and using its new
registry digest; updating the host-side runner alone does not update deployed
fixture code. The state-write endpoint accepts both fixed-length and streamed
HTTP/1.1 chunked JSON, with a 256-byte decoded-body limit, bounded framing and
read timeout. Invalid or ambiguous framing returns `400 invalid_marker` before
accessing PostgreSQL. Regression tests exercise the real authorizer/proxy's
chunked forwarding into the HTTP fixture, including durable PostgreSQL read-back.

Before a live run, wildcard application DNS, public HTTPS certificates trusted
by the host and fixture container, the hosted authorizer/proxy, the provisioner's
existing client/user-management permissions, and available workload capacity
must be ready. Approve the provider and issuer's apply-time IP addresses on TCP
443 through the normal operator egress configuration. The harness neither
widens that allow-list nor disables TLS checks. Supply a resolvable unrelated
host outside those permitted addresses for the negative egress assertion. Its TCP
443 endpoint must be reachable from the platform host in the fixture Pods' IP
families so that the harness can establish an outside-policy positive control.
The operator needs access to the host's private `.env`, `kubectl`, and
`.runtime/admin.kubeconfig`. Override `--kubectl` or `--settings` if necessary.

Use the [private operator-session procedure](#obtain-a-private-operator-session-for-the-hosted-access-harness)
below to authenticate an existing **human platform administrator**. It saves a mode
`0600` JSON session file containing exactly `access_token`, `refresh_token`, and
`client_id` (normally `platform-cli`). Do not supply passwords, bearer tokens,
refresh tokens, or client secrets as command arguments. The harness renews the
operator session in memory; it never writes renewed credentials to the journal.
Obtain a fresh session for crash recovery if the original session is no longer
usable. The existing operator account and its grants are not changed.

### Update the runner without redeploying platform services

A runner/fixture-only release does not require `ansible/deploy.yml`. From the
controller checkout of the intended release, transfer the changed runner module
to the existing installation (substitute the actual host/install directory):

```bash
scp platform/acceptance/harness.py \
  root@node-01.eseidinger.de:/opt/developer-platform/platform/acceptance/harness.py
```

Run `sha256sum platform/acceptance/harness.py` on both sides and confirm they
match. For a release that also changes runner dependencies, the entry point or
other runner modules, update those files and the runner environment as well;
copying this single file is sufficient only when those inputs are unchanged.
On the host set `HA_IMAGE` to the new published fixture's immutable registry
digest before generating a fresh plan/run ID. Copying fixture source onto the
host does not update its container image. This transfer does not update the
control-plane revision in `.runtime/installation-record.json`; record runner
hash and fixture digest separately. Changes to platform services still require
the supported deployment procedure.

### Obtain a private operator session for the hosted-access harness

Run on the platform host from its installation directory in a trusted shell
with tracing disabled. Keep `.runtime` private and do not share the printed
approval URL, session file, or tokens. Set the actual HTTPS issuer; for the local
development CA, also set `SSL_CERT_FILE` to the trusted CA file (the Python
example does not use `CURL_CA_BUNDLE`). Never disable certificate verification.
Copy the self-contained example below into the host shell: deployment transfers
runtime sources, not this `docs/` tree, so do not try to execute or extract it
from a Markdown file under `/opt/developer-platform`.

```bash
cd /opt/developer-platform
umask 077
export ISSUER='https://identity.eseidinger.de/realms/platform'

python3 - <<'PY'
import base64
import hashlib
import json
import os
import secrets
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

issuer = os.environ["ISSUER"].rstrip("/")
parts = urllib.parse.urlsplit(issuer)
if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
    raise SystemExit("Use the configured HTTPS issuer without credentials or query parameters.")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

context = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))
opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))

def post(path, fields):
    request = urllib.request.Request(
        issuer + "/protocol/openid-connect/" + path,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    try:
        with opener.open(request, timeout=15) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code != 400:
            raise SystemExit("Identity endpoint rejected the request; nothing saved.")
        try:
            result = json.load(error)
        except ValueError:
            raise SystemExit("Identity endpoint returned an unexpected response.")
    except urllib.error.URLError:
        raise SystemExit("Identity endpoint could not be reached.")
    except ValueError:
        raise SystemExit("Identity endpoint returned an unexpected response.")
    if not isinstance(result, dict):
        raise SystemExit("Identity endpoint returned an unexpected response.")
    return result

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
device = post("auth/device", {
    "client_id": "platform-cli", "scope": "openid",
    "code_challenge": challenge, "code_challenge_method": "S256",
})
if not all(device.get(key) for key in ("device_code", "verification_uri_complete", "expires_in")):
    raise SystemExit("Device authorization could not be started.")

print("Open:", device["verification_uri_complete"], flush=True)
print("Sign in as your human platform administrator and approve.", flush=True)
interval = max(1, int(device.get("interval", 5)))
deadline = time.monotonic() + int(device["expires_in"])
while time.monotonic() < deadline:
    result = post("token", {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": "platform-cli", "device_code": device["device_code"], "code_verifier": verifier,
    })
    if "access_token" in result:
        if not all(isinstance(result.get(key), str) and result[key] for key in ("access_token", "refresh_token")):
            raise SystemExit("No complete renewable session returned; nothing saved.")
        session = {key: result[key] for key in ("access_token", "refresh_token")}
        session["client_id"] = "platform-cli"
        fd, temporary = tempfile.mkstemp(prefix=".operator-session-", dir=".runtime")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(session, output)
            os.replace(temporary, ".runtime/operator-session.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print("Saved private operator session (permissions 600).")
        break
    error = result.get("error")
    if error == "slow_down":
        interval += 5
    elif error != "authorization_pending":
        raise SystemExit("Authorization failed or expired; rerun this command.")
    time.sleep(min(interval, max(0, deadline - time.monotonic())))
else:
    raise SystemExit("Device approval expired; rerun this command.")
PY
```

Open the printed URL while the command is polling; approval must finish before
the device code expires. `authorization_pending` and `slow_down` are expected
polling responses, not reasons to pipe an empty response into a JSON parser.
Success atomically replaces `.runtime/operator-session.json` with exactly
`access_token`, `refresh_token`, and `client_id`, mode `0600`. A rejected, expired,
or incomplete exchange leaves an existing session untouched; do not run the
harness until a fresh save succeeds. Avoid `curl --fail | … > session.json`,
which can truncate the session before authentication succeeds. The harness does
not persist rotated refresh tokens, so obtain a fresh session for subsequent
runs or cleanup retries. A successful login still requires an existing human
platform-admin grant, which the harness checks before provisioning.

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
  --unrelated-host eseidinger.de
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
Network isolation checks require successful TCP controls to the same resolved
addresses immediately before and after each negative probe. Backend controls
run from the existing authorizer; the unrelated-egress control runs from the
platform host. The harness does not create a probe Pod or change network policies.
Timeouts and active connection refusals can count as denial only with these
controls. DNS failures, address changes, unexpected network errors, unavailable
controls, or any successful negative connection fail the check. Probes cover the
ready source Pods' configured IPv4/IPv6 families; absence of IPv6 routing on an
IPv4-only cluster is not treated as isolation evidence. Reports contain only
outcome counts, family flags, and control-success flags for these probes, never
raw exception text or response bodies.

`--timed` additionally holds a real machine token until expiry (up to five
minutes). `--allow-recovery-reconcile` separately authorizes the **global**
catalog-to-identity-provider reconciliation endpoint, so it requires an isolated
lab with no other project records, including retired records. It verifies stable
principals and state, invalidated browser sessions and old machine credentials,
and replacement credentials. This is a reconciliation rehearsal, **not** a
backup restore, and it cannot establish backup/recovery acceptance. Do not use
the flag on a shared lab; the inventory check cannot prevent concurrent creation
of another project, so reserve the lab for the duration of the drill.

`--monitoring` additionally checks neutral component URLs, protected-boundary
probes, Kubernetes readiness and provider/consumer central correlation through
authorized retained-log reads. Prometheus defaults to operator-local
`http://127.0.0.1:9090`; `--prometheus` selects another trusted operator origin.
Deploy PLAN-017 source first and publish a new fixture digest: the EV-45 fixture
does not emit operational envelopes. Checks run before retirement without granting
monitoring application access. The report keeps the monitoring/retention check
deferred even on success: immediate ingestion does not prove seven elapsed days
or compactor deletion. EV-45 remains historical evidence, not evidence for this
new increment.

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

The PostgreSQL isolation check records `writeHttpStatus`,
`consumerReadHttpStatus`, `writeMarkerMatches`, and `consumerMarkerMatches`;
the restart read-back check records `readHttpStatus`. A pass requires the write
response to match the durable synthetic marker, the consumer to retain its own
initial marker, and the provider to return the durable marker after restart.
Only statuses and comparison booleans are included, not markers or response
bodies. A `400` write status indicates rejected input/framing, not proof of a
PostgreSQL provisioning or network failure.

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
`hosted_access_timed`, `hosted_access_monitoring`, and
`hosted_access_allow_recovery_reconcile`, all false by default.
`hosted_access_prometheus` defaults to target loopback port 9090.
It does not transfer credentials or install dependencies.

Local verification: the offline/safety/fixture tests pass, the fixture image
builds, and its non-root/read-only readiness and real PostgreSQL persistence
checks pass against disposable containers. These checks do not contact the
running platform or substitute for the live acceptance run.

## Executed hosted-access core acceptance: October 11, 2026

Evidence ID: [EV-45](../../maintainers/delivery/backlog.md#verification-register).
Source: the operator-provided `report.json` from the live node-01 lab, reviewed
after the run. This documentation records that report; it is not an independent
rerun, a fresh host inspection, or full Phase 3/F-10 acceptance.

### Run identity and retained evidence

- Run ID: `c927adee1d50`.
- Environment: `node-01.eseidinger.de`, installation `/opt/developer-platform`,
  API `http://127.0.0.1:8000`, application domain `apps.eseidinger.de`, and
  identity issuer `https://identity.eseidinger.de/realms/platform`.
- Started: `2026-10-11T16:34:39.146765+00:00`; finished:
  `2026-10-11T16:47:23.031161+00:00` (UTC; approximately 12 minutes 44 seconds).
- Result: `core-passed`; all 39 named checks passed; `gateClosed: false`.
- Requested drills: held machine-token expiry enabled (`--timed`); global
  recovery reconciliation not enabled.
- Runner/fixture release: `hosted-access-v0.1.2`, source commit
  `e8f74fdd522ab18bd06ffed06073525494a90345`. The runner was updated separately
  from platform services. The report does not identify the deployed control-plane
  source revision; this release reference is not a runtime-version assertion.
- Harness SHA-256:
  `e57bb05502634e1f40666be57e3224e2bbd0df80391164c19082541e204c5f00`.
- Fixture image:
  `docker.io/eseidinger/developer-platform-acceptance-fixture@sha256:e0f18af69dc24e285624c29a2aa0aa676f42b11493cc0e1ade94a52ffaee85e4`.
- Projects: `ha-c927adee1d50-provider` and `ha-c927adee1d50-consumer`, both
  revision 1, each with a public API and private worker. Per component: CPU
  request/limit `50m`/`250m`; memory request/limit `64Mi`/`128Mi`.
- Private evidence remains on the host at
  `/opt/developer-platform/.runtime/hosted-access/c927adee1d50/report.json`, with
  cleanup handles in the adjacent `state.json`. Classification: Internal;
  preserve the journal under the approved evidence-retention policy. Do not
  copy the operator session, credentials, or raw identity claims into Git.

### Passed scope

The 39 named assertions cover:

- Digest-pinned readiness of two projects/four components; pending first human
  login despite platform-admin status; explicit human approval and bounded
  claim refresh; withheld optional personal attributes; secure browser cookies,
  CSRF protection, and stable identity after rename.
- Machine audience and client-scoped groups; missing/invalid/wrong-audience
  token rejection (`401`); wrong-group/unmatched/segment-prefix rejection
  (`403`); encoded-slash rejection (`400`); `HEAD`/explicit `OPTIONS`; replacement
  of forged identity headers and stripping of the bearer token; denial of a
  valid but unapproved machine.
- Project-wide service binding visible to the private worker, successful
  consumer-to-provider public HTTPS through the managed credential, and hashed
  synthetic cross-project correlation.
- Provider and consumer direct-backend bypass denial, unrelated-egress denial,
  and DNS-address-pinned egress. Every negative probe had healthy same-address
  controls before and after. Both backend probes had zero connections and one
  active refusal; the unrelated-egress probe had zero connections and two
  active refusals. No timeout, DNS error, address mismatch, or unexpected error
  supplied the denial evidence. Probes covered IPv4 only (`ipvSix: false`);
  this run does not demonstrate IPv6 isolation. The report captured four pinned
  CIDR entries (two unique addresses), including an IPv6 pin, which is not proof
  of IPv6 connectivity or enforcement.
- Separate project PostgreSQL state, preservation of provider revision across
  restart, and read-back of the durable marker after restart. Write and consumer
  read both returned `200`, both marker comparisons passed, and post-restart
  read returned `200`; this validates the chunked fixture-write fix in the
  deployed path without exposing marker values.
- Rejection of overlapping policies, restrictive-policy activation and immutable
  rollback; stable principal during normal/emergency rotation, bounded normal
  overlap, adoption revoking the old client, and no emergency overlap.
- Expiry denial of an already issued machine token and revocation denial of an
  existing human session and an already issued machine token.

| Measurement | Observed seconds |
|---|---:|
| Human approval and bounded claim refresh | 241.453 |
| Normal adoption revokes old client | 0.006 |
| Emergency no-overlap check | 0.006 |
| Held machine token until expiry denial | 300.131 |
| Human revocation with existing session | 2.357 |
| Machine revocation with issued token | 2.310 |

These are this run's measurements, not latency guarantees. In particular,
healthy-system revocation results do not prove the dependency-outage bound.

### Cleanup and remaining acceptance

Cleanup reported `completed-data-retained`: the harness completed fixture
retirement and synthetic identity cleanup while retaining the synthetic
PostgreSQL databases. No cleanup retry is indicated. Database purge is a
separate operator decision; do not infer permission to delete retained data.

The report explicitly leaves these nine checks deferred:

- `real-backup-restore`
- `browser-30-minute-idle-and-8-hour-absolute-expiry`
- `24-hour-rotation-adoption-timeout`
- `30/90-day-request-retention`
- `component-monitoring-and-central-log-retention`
- `control-plane-outage`
- `dns-address-change-reapply`
- `recovery-reconciliation-rehearsal`
- `external-use-case-suite`

The held-machine-token expiry check is no longer deferred for this run.
PLAN-009, PLAN-018, PLAN-019, F-10 and the Phase 10 gate remain open; component
monitoring/centralized log retention also remains PLAN-017 work. Recovery
reconciliation, even when subsequently exercised, is not a real backup restore.
Concrete energy declarations, governance records, domain authorization, and
deterministic energy-workflow outcomes remain externally owned and unverified by
this neutral suite.

## Executed hosted-access monitoring acceptance: October 11, 2026

Evidence ID: [EV-46](../../maintainers/delivery/backlog.md#verification-register).
Source: the operator-provided live node-01 `report.json`, following the
operator-confirmed deployment and healthy Alloy startup. This records supplied
evidence, not an independent rerun or full Phase 3/F-10 acceptance. EV-45 remains
the earlier historical core run.

### Run identity

- Run ID: `60c3ca1647b9`, using the same host, installation, API, application
  domain and issuer as EV-45.
- Started: `2026-10-11T19:02:34.656777+00:00`; finished:
  `2026-10-11T19:14:55.483297+00:00` (UTC; approximately 12 minutes 21 seconds).
- Result: `core-passed`, all 45 named assertions passed, `gateClosed: false`.
- Requested drills: `tokenExpiry: true`, `componentMonitoring: true`,
  `recoveryReconcile: false` (`--timed --monitoring`, without global reconcile).
- Runner/fixture release: `hosted-access-v0.2.0`, source
  `b360ddee34444748c95705c597aa7b17491cd05b`. The Alloy UID/GID and readiness fix
  was implemented and the operator reported redeployment before this run.
  That fix was not part of the fixture release and requires no new fixture
  image. The report does not attest the exact deployed control-plane revision
  or working-tree contents; do not treat the release as that attestation.
- Harness SHA-256:
  `baa046e028656dfe9dc45c578390bcd33923e2c25b20dbd84313b2cbc5ab845c`.
- Fixture image:
  `docker.io/eseidinger/developer-platform-acceptance-fixture@sha256:5c14c1bedfc653e98f958b88deacc5af488f885a5d9a6d3b96e9325938b3f0ad`.
- Projects: `ha-60c3ca1647b9-provider` and `ha-60c3ca1647b9-consumer`, each
  revision 1 with a public API and private worker; CPU request/limit
  `50m`/`250m`, memory request/limit `64Mi`/`128Mi` per component.
- Private report:
  `/opt/developer-platform/.runtime/hosted-access/60c3ca1647b9/report.json`;
  adjacent `state.json` contains cleanup handles. Classification: Internal;
  retain under the approved evidence policy. Do not commit sessions, credentials
  or raw identity claims.

### Deployed monitoring scope and core regression

The 39 core assertions described in EV-45 passed again. Six additional checks
passed before fixture retirement:

| Named check | UTC observation |
|---|---|
| `provider-component-public-boundary-probe` | 19:07:26.310652 |
| `provider-component-semantic-readiness` | 19:07:26.314516 |
| `provider-centralized-safe-correlation` | 19:07:28.614805 |
| `consumer-component-public-boundary-probe` | 19:07:28.617914 |
| `consumer-component-semantic-readiness` | 19:07:28.620554 |
| `consumer-centralized-safe-correlation` | 19:07:28.696688 |

For each project, the public probe matched its API component's declared
`/health/ready` URL with `probe_kind=access-boundary` and successful login/denial
semantics. Kubernetes ready-pod metrics independently supplied semantic readiness.
Project-authorized retained-log reads found the expected opaque synthetic
correlation, revision `1` and populated operation metadata. These reads prove
safe-envelope retrieval through the API; they do not certify arbitrary raw-log
storage or customer/domain correlation. The monitoring summary records
`componentProbes: passed`, `centralIngestion: passed` and
`sevenDayRetention: not-time-verified`.

Core PostgreSQL write/read and restart read-back returned `200`; marker
comparisons passed. Backend bypass and unrelated-egress checks had healthy
same-address controls before and after, with no successful negative connection,
timeout, DNS error, address mismatch or unexpected error. The tested network
family was IPv4 only; IPv6 CIDR pins are not IPv6 isolation evidence.
Measured approval/claim refresh was 241.681 seconds; normal adoption revocation
0.006 seconds; emergency no-overlap 0.005 seconds; held-token expiry denial
298.127 seconds; existing-human-session revocation 2.338 seconds and issued
machine-token revocation 2.240 seconds. These are observations, not guarantees
or dependency-outage evidence.

### Collector repair, cleanup and remaining acceptance

The preceding run `3c17ed6dcdac` failed with
`component_retained_correlation_unavailable`; cleanup completed with data retained.
The operator's collector output showed a restart loop caused by
`mkdir /var/lib/alloy/remotecfg: permission denied`. The pinned image's state
directory is `473:473`, mode `0770`; UID `0` with GID `0` and all capabilities
dropped could not write it. The repair uses `0:473`, retains the named state
volume and hardening, adds an internal readiness check, and makes bootstrap wait
for collector health. The operator confirmed healthy Alloy and running Loki
before the successful rerun. Separate disposable local fixtures reproduced the
old failure and verified production-volume startup/restart, ingestion and Loki
restart readback; those local tests are not live retention evidence.

Cleanup for `60c3ca1647b9` reported `completed-data-retained`; no retry is
indicated. Retained databases must not be purged without a separate decision.
The same nine deferred checks listed for EV-45 remain deferred, including the
combined `component-monitoring-and-central-log-retention` entry: deployed probes
and immediate ingestion now have evidence, but seven elapsed days and compactor
deletion do not. This run does not query retained logs after workload restart or
cleanup, exercise collector/backend outages, or verify alert delivery.
Record post-retirement/restart readback and a seven-day retention-boundary drill
with collector/backend health, collection gaps and compactor delay before
closing PLAN-017. PLAN-009, PLAN-018, PLAN-019, F-10 and Phase 10 remain open;
the externally owned energy suite and configuration contract are unchanged.

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
       https://platform.eseidinger.de/projects
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
