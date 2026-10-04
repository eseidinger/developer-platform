# Fresh Deployment and Basic Platform Tests

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

Follow [Keycloak bootstrap](keycloak-bootstrap.md) to create the initial individual platform administrator and remove `PLATFORM_BOOTSTRAP_SUBJECT` after the one-time grant is recorded. Create separate developer and project-administrator users; never share the Keycloak administrator or a human access token with automation.

Grant project roles through the Platform API, then run the [human access and authorization validation](human-access-and-authorization-validation.md) matrix.

## 3. Bootstrap the automation test runner once

Use a current human platform-administrator token once to create the privileged, expiring test-runner client. Choose an output path outside the repository on encrypted or otherwise protected storage:

```bash
ansible-playbook ansible/bootstrap-platform-test-runner.yml \
  -e @/path/to/protected-human-bootstrap-vars.yml
```

The protected input supplies `platform_api_url`, `platform_human_admin_token`, and `platform_test_runner_output`. The playbook writes mode `0600` JSON containing the runner client ID, one-time returned client secret, token URL, credential ID, and expiry. Remove the human token from the automation configuration after bootstrap. The client secret is reusable until expiry, rotation, or revocation; each suite run exchanges it for a fresh short-lived bearer token.

Only a human platform administrator can create, list, rotate, or revoke a root test runner. The runner can create disposable projects and temporary role personas, but it cannot mint another runner.

## 4. Run basic platform tests without a human token

Run the suite with the protected bootstrap output as its variable file:

```bash
ansible-playbook ansible/test-platform.yml \
  -e @/path/to/protected-test-runner.json
```

The suite creates two unique empty projects, creates short-lived viewer, developer, and project-administrator service-account personas, verifies role and cross-project boundaries, creates a project deployment credential, and performs the project's first application deployment with it. It also exercises configuration, bounded credential rotation, immediate old-token denial, revocation, and best-effort cleanup from an Ansible `always` block. All client-secret and bearer-token tasks use `no_log: true`; the final report contains only the test-run ID and deployed revision.

These personas test Platform API authorization through the same immutable OIDC subject and platform-owned grant path as human principals. They do not test an interactive browser login or a user's password flow.

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

## 6. Additional manual checks

Run, in order:

1. API readiness and Kubernetes node readiness.
2. Human authentication and project-role authorization checks.
3. A normal application deployment and operation/readiness observation.
4. The automation suite: empty-project creation, persona token acquisition, first CI deployment, scoped reads, denied privileged/cross-project actions, rotation, old-token denial, revocation, and cleanup.
5. Project logs, status, revision, rollback, restart, and retirement-preview checks appropriate to the deployed feature set.

Use disposable test project names and record the deployed revision and installation record. Do not claim multi-service Phase 2A acceptance while its live checks are deferred.

## Separate operational tracks

- [Backup and recovery](backup-recovery.md) and `operations/backup/`
- [External watchdog](../../operations/watchdog/README.md)
- [Heartbeat and availability drills](../../operations/heartbeat/README.md)
- [Alertmanager email delivery](../../operations/alertmanager/README.md)
- [Monitoring operations](monitoring.md)

Install and test these after the basic platform path when their own inventories and protected credentials are ready. Their tests are not part of basic user/token setup.
