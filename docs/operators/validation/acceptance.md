# Fresh deployment and platform acceptance

Status: current acceptance procedure. Individual evidence remains scoped to the
recorded revision and environment.

This guide covers a clean platform installation, basic human identities, revocable CI deployment credentials, and core platform tests. Backup, external watchdog, heartbeat availability drills, and Alertmanager delivery are separate operational tracks; they are not prerequisites for this sequence.

## 1. Deploy the platform

Prepare DNS, an Ubuntu 22.04+ host, SSH access, Python 3, systemd, and the capacity described in the repository README. From a trusted controller:

```bash
python3 -m pip install 'ansible-core>=2.16'
cp ansible/inventory.example.yml ansible/inventory.yml
# Set host, SSH user, platform/app/identity domains, TLS email and edge bind address.
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --ask-become-pass
```

On the host, verify the installation before creating users:

```bash
cd /opt/developer-platform
sudo docker compose ps
curl --fail https://PLATFORM_DOMAIN/readyz
sudo kubectl --kubeconfig .runtime/admin.kubeconfig get nodes
sudo cat .runtime/installation-record.json
```

## 2. Create basic human users

Follow [Keycloak bootstrap](../identity-and-access.md) to create the initial individual platform administrator and remove `PLATFORM_BOOTSTRAP_SUBJECT` after the one-time grant is recorded. Create separate developer and project-administrator users; never share the Keycloak administrator or a human access token with automation.

Grant project roles through the Platform API, then run the [human access and authorization validation](access-and-authorization.md) matrix.

## 3. Bootstrap the automation test runner once

Use a current human platform-administrator token once to create the privileged, expiring test-runner client. Choose an output path outside the repository on encrypted or otherwise protected storage **on the controller running Ansible**, not on the platform host. Create its parent directory first with restrictive permissions; the playbook refuses a missing, unwritable, or existing output path before creating the one-time credential:

```bash
ansible-playbook ansible/bootstrap-platform-test-runner.yml \
  -e @/path/to/protected-human-bootstrap-vars.yml
```

The protected input supplies `platform_api_url`, `platform_human_admin_token`, and `platform_test_runner_output`. The playbook writes mode `0600` JSON containing the runner client ID, one-time returned client secret, token URL, credential ID, and expiry. Remove the human token from the automation configuration after bootstrap. The client secret is reusable until expiry, rotation, or revocation; each suite run exchanges it for a fresh short-lived bearer token.

Only a human platform administrator can create, list, rotate, or revoke a root test runner. The runner can create disposable projects and temporary role personas, but it cannot mint another runner.

To deliberately remove a runner, use a separate protected file containing
`platform_api_url` and `platform_human_admin_token`. The runner JSON and its
credential ID are not needed. The playbook resolves exactly one active runner by
name and refuses an absent or ambiguous match. The explicit confirmation prevents
that name from being revoked accidentally:

```bash
ansible-playbook ansible/revoke-platform-test-runner.yml \
  -e @/path/to/protected-human-admin-vars.yml \
  -e platform_confirm_test_runner_revocation=platform-acceptance-suite
```

Set `platform_test_runner_name` and the same confirmation value to revoke a
different named runner. The command is irreversible: a replacement runner must
be bootstrapped with a human token and receives a new one-time secret.

## 4. Run basic platform tests without a human token

Run the suite with the protected bootstrap output as its variable file:

```bash
ansible-playbook ansible/test-platform.yml \
  -e @/path/to/protected-test-runner.json
```

The suite creates two unique empty projects, creates short-lived viewer, developer, and project-administrator service-account personas, verifies role and cross-project boundaries, creates a project deployment credential, and performs the project's first application deployment with it. It also exercises configuration, bounded credential rotation, immediate old-token denial, revocation, and best-effort cleanup from an Ansible `always` block. All client-secret and bearer-token tasks use `no_log: true`; the final report contains only the test-run ID and deployed revision.

These personas test Platform API authorization through the same immutable OIDC subject and platform-owned grant path as human principals. They do not test an interactive browser login or a user's password flow.

## 4A. Run the automated multi-service and scheduled-component acceptance suite

After the basic suite, run the Phase 2A suite from a controller with the normal
platform inventory. It uses the protected runner configuration, creates a unique
disposable project and administrator persona, and delegates only read-only
Kubernetes object checks to the platform host:

```bash
ansible-playbook -i ansible/inventory.yml \
  ansible/test-platform-components.yml \
  -e @/path/to/protected-test-runner.json
```

The suite waits for a real minute-based CronJob run and may take several minutes.
It verifies legacy-to-component revision history, two ready internal services,
scheduled access to both stable service names, `Forbid` non-overlap observed on
each poll, invalid-cron rejection, an API-only update that leaves the peer
Deployment generation unchanged, and a component-aware retirement preview. It
always attempts to retire the disposable project and revoke its temporary persona.
It assumes the inventory connects to the platform host as `root` and therefore
does not invoke `sudo`. If the inventory instead uses an unprivileged SSH user,
set `platform_component_drill_become=true` and provide that host's normal Ansible
become credentials through an encrypted inventory or vars file.

This does not replace the separate backup/recovery procedures. Triggering and
inspecting encrypted backup storage requires distinct protected credentials and
is kept in the [backup and recovery](../backup-and-recovery.md) track.

## 5. Create a real empty project for later CI deployment

A platform administrator creates the durable scope without submitting an application:

```http
POST /projects
Authorization: Bearer <human-platform-admin-token>
Content-Type: application/json

{"name":"example"}
```

The project is returned with `status: empty` and `spec: null`. Grant a human project administrator through `PUT /projects/example/grants`. That administrator creates a project-scoped deployment credential through `POST /projects/example/deployment-credentials` and stores the one-time returned client secret directly in the CI secret store.

Exchange the client ID and secret at the issuer token endpoint with the OAuth 2.0 client-credentials grant. Use the returned short-lived bearer token for deployment and observation only. List responses never return the secret. Rotation creates a replacement credential; revocation removes the platform grant before provider cleanup, so the next request is denied even if an issued token has not expired.

The existing desired-state endpoint performs the first and later deployments:

```http
PUT /projects/example
Authorization: Bearer <short-lived-CI-token>
Content-Type: application/json

{"name":"example","image":"registry.example/application:release","port":8080}
```

The focused legacy `test-platform-ci-credential.yml` remains available when an operator specifically wants to test an already prepared project's credential path with a protected project-administrator token. The normal fresh-deployment acceptance path is `test-platform.yml` and does not retain a human token.

## 6. Optional credential lifecycle drills (accepted as deferred)

The routine suite has already exercised creation, scoped access, rotation, and
immediate revocation. The following two higher-cost drills are automated but are
**accepted as deferred for the current lab**. They are not required for routine
CI or for the basic platform test sequence. Record a new owner decision before
making either a release gate.

### Scheduled expiry verification

Create a separate, one-day test runner; do not reuse the normal acceptance runner.
Use a new protected output path and run its active check immediately:

```bash
ansible-playbook ansible/bootstrap-platform-test-runner.yml \
  -e @/path/to/protected-human-bootstrap-vars.yml \
  -e platform_test_runner_name=platform-expiry-drill \
  -e platform_test_runner_expires_in_days=1 \
  -e platform_test_runner_output=/path/to/protected-expiry-drill.json

ansible-playbook ansible/verify-platform-test-runner-expiry.yml \
  -e @/path/to/protected-expiry-drill.json \
  -e platform_expiry_drill_phase=active
```

Schedule the same verifier after the `platform_test_runner_expires_at` timestamp
written to that protected file, with a small delay for clock skew:

```bash
ansible-playbook ansible/verify-platform-test-runner-expiry.yml \
  -e @/path/to/protected-expiry-drill.json \
  -e platform_expiry_drill_phase=expired
```

The second invocation passes only when the client-credentials exchange returns
`400` or `401`. Its report includes only the credential ID and expiry timestamp.

### Controlled identity-provider outage verification

This drill stops Keycloak on the deployed host. Run it only in an approved
maintenance window, from a controller that can SSH to the `platform` host in the
normal inventory. Provide a disposable existing project and its protected human
project-administrator token outside the repository:

```bash
ansible-playbook -i ansible/inventory.yml \
  ansible/test-platform-identity-provider-outage.yml \
  -e platform_api_url=https://platform.example.com \
  -e platform_test_project=disposable-outage-drill \
  -e platform_identity_drill_host=platform \
  -e @/path/to/protected-project-admin-vars.yml \
  -e platform_allow_identity_outage_drill=true \
  -e platform_identity_outage_acknowledgement=I_ACCEPT_IDENTITY_OUTAGE
```

The playbook creates a disposable credential, proves it works, stops Keycloak,
requires `revocation_pending` and immediate denial of the issued token, then
restores Keycloak in an `always` block and requires final `revoked` cleanup. It
does not print client secrets or bearer tokens. If a failed controller connection
prevents Ansible from reaching the `always` block, restore the service manually
on the host with `sudo docker compose up -d --wait keycloak` from
`/opt/developer-platform`.

## 7. Additional manual checks

Run, in order:

1. API readiness and Kubernetes node readiness.
2. Human authentication and project-role authorization checks.
3. A normal application deployment and operation/readiness observation.
4. The automation suite: empty-project creation, persona token acquisition, first CI deployment, scoped reads, denied privileged/cross-project actions, rotation, old-token denial, revocation, and cleanup.
5. Project logs, status, revision, rollback, restart, and retirement-preview checks appropriate to the deployed feature set.

Use disposable test project names and record the deployed revision and installation record. Phase 2A acceptance is recorded as EV-38 with owner-accepted deferrals for database-row preservation, backup inventory, and representative capacity measurement.

## Separate operational tracks

- [Backup and recovery](../backup-and-recovery.md) and `operations/backup/`
- [External watchdog](../../../operations/watchdog/README.md)
- [Heartbeat and availability drills](../../../operations/heartbeat/README.md)
- [Alertmanager email delivery](../../../operations/alertmanager/README.md)
- [Monitoring operations](../monitoring.md)

Install and test these after the basic platform path when their own inventories and protected credentials are ready. Their tests are not part of basic user/token setup.
