# Local installation

Status: current. Last reviewed October 18, 2026.

## Prerequisites

- Linux or WSL2 with Docker Engine and Compose 2.20.3 or newer
- Python 3.10 or newer for host scripts, Bash, `setfacl` (Linux `acl` package),
  and kubectl 1.35.x–1.37.x; API/CLI source development requires Python 3.12+
- Root access and `mount`, `findmnt`, `mountpoint`, `mkfs.ext4`, and `truncate`
  to prepare the bounded Tempo filesystem
- Internet access and access to Linux cgroups/privileged k3d containers
- Suggested capacity: 16 vCPUs and 32 GB RAM

Run from the repository root:

```bash
python3 scripts/init.py
python3 scripts/setup/install-k3d.py
sudo bash scripts/setup/prepare-tempo-storage.sh
docker compose up -d postgres keycloak-db-init keycloak proxy
```

`init.py` creates missing secrets in the git-ignored `.env` and preserves
existing values. The k3d installer verifies its download. Bootstrap later writes
the admin kubeconfig to `.runtime/admin.kubeconfig` without changing the default
context. Tempo preparation mounts a dedicated 4 GiB filesystem at
`/var/lib/developer-platform/tempo`. Run the preparation command after each host
reboot before bootstrap; there is no persistent mount entry installed by this
script. `scripts/up.sh` refuses to start without that mount.

Local `.env` validation and controlled redeployment use the same
[configuration and deployment commands](configuration-and-deployment.md) as
Ansible. Routine startup remains `bash scripts/up.sh`.

## Bootstrap identity

For noninteractive local setup, wait until the `keycloak-realm-init` service has
finished successfully, then run:

```bash
python3 scripts/setup/bootstrap-local-admin.py
```

This creates an account using your local username (override with `--username`),
writes its temporary password to mode-`0600` `.runtime/initial-admin.json`, and
sets `PLATFORM_BOOTSTRAP_SUBJECT` to the new account's immutable ID. Keycloak
requires a password change at first login. The command refuses to reset an
existing account or overwrite a recovery file. A lost create response leaves
the private recovery file intact for investigation. Automation uses separate
test identities and never consumes this initial administrator password.

Run `bash scripts/up.sh` next. After the first administrator grant has been
persisted, clear `PLATFORM_BOOTSTRAP_SUBJECT` and recreate the API container so
the one-time setting is removed from its environment.

Alternatively, configure the first account manually:

Open `http://identity.localhost`, sign in as Keycloak `admin` with the password
from `.env`, and create the initial individual user in the `platform` realm. Put
that user's immutable ID in `PLATFORM_BOOTSTRAP_SUBJECT`, then run
`bash scripts/up.sh` to start the API and remaining services. Remove the setting
after the first platform-admin grant exists. Follow
[Identity and access](identity-and-access.md) for the complete procedure.

## Verify

```bash
docker compose ps
curl --fail-with-body http://127.0.0.1:8000/healthz
curl --fail-with-body http://127.0.0.1:8000/readyz
kubectl --kubeconfig .runtime/admin.kubeconfig get pods -A
# Set SMOKE_FIXTURE_IMAGE to a digest-pinned http-echo image first.
uv run --project platform/app python scripts/tests/platform/smoke.py plan \
  --run-id 0123456789ab --fixture-image "$SMOKE_FIXTURE_IMAGE"
```

The smoke plan is offline. For the explicit live command and credentials, see
the [script test guide](../../scripts/tests/README.md). Live runs create a unique
project and retire it afterward, retaining SQL data. `/healthz` proves only API
process health
and `/readyz` checks PostgreSQL plus Kubernetes connectivity; neither proves
every workload. Use [platform acceptance](validation/acceptance.md) for the
broader suite and [lifecycle](lifecycle.md) for stop, restart, recreation, and
cleanup.

## Noninteractive functional tests

Once the API is ready, follow the
[test-runner bootstrap](../../ansible/docs/test-runner.md#local-bootstrap-without-interactive-login)
to issue a one-day, private machine credential using local Docker access.
Routine runners renew tokens without a human login. Initial administrator
configuration and tests of human authentication remain separate requirements.
