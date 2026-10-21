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

`init.py` creates missing secrets in the git-ignored `.env` and preserves existing
values. The k3d installer verifies its download. Bootstrap later writes the admin
kubeconfig to `.runtime/admin.kubeconfig` without changing the default context.
Tempo preparation mounts a dedicated 4 GiB filesystem at
`/var/lib/developer-platform/tempo`. Run the preparation command after each host
reboot before bootstrap; there is no persistent mount entry installed by this
script. `scripts/up.sh` refuses to start without that mount.

## Bootstrap identity

Open `http://identity.localhost`, sign in as Keycloak `admin` with the password
from `.env`, and create the initial individual user in the `platform` realm. Put
that user's immutable ID in `PLATFORM_BOOTSTRAP_SUBJECT`, then run
`bash scripts/up.sh` to start the API and remaining services. Remove
the setting after the first platform-admin grant exists. Follow
[Identity and access](identity-and-access.md) for the complete procedure.

## Verify

```bash
docker compose ps
curl --fail-with-body http://127.0.0.1:8000/healthz
curl --fail-with-body http://127.0.0.1:8000/readyz
kubectl --kubeconfig .runtime/admin.kubeconfig get pods -A
# Obtain and export a short-lived administrator PLATFORM_ACCESS_TOKEN first.
python3 scripts/acceptance/smoke.py
```

The smoke test retains its project. `/healthz` proves only API process health and
`/readyz` checks PostgreSQL plus Kubernetes connectivity; neither proves every
workload. Use [platform acceptance](validation/acceptance.md) for the broader
suite and [lifecycle](lifecycle.md) for stop, restart, recreation, and cleanup.
