# Local installation

Status: current. Last reviewed October 9, 2026.

## Prerequisites

- Linux or WSL2 with Docker Engine and Compose 2.20.3 or newer
- Python 3.10 or newer, Bash, and kubectl 1.35.x–1.37.x
- Internet access and access to Linux cgroups/privileged k3d containers
- Suggested capacity: 16 vCPUs and 32 GB RAM

Run from the repository root:

```bash
python3 scripts/init.py
python3 scripts/install-k3d.py
docker compose up -d postgres keycloak-db-init keycloak proxy
bash scripts/up.sh
```

`init.py` creates missing secrets in the git-ignored `.env` and preserves existing
values. The k3d installer verifies its download and keeps the admin kubeconfig at
`.runtime/admin.kubeconfig` without changing the default kubectl context.

## Bootstrap identity

Open `http://identity.localhost`, sign in as Keycloak `admin` with the password
from `.env`, and create the initial individual user in the `platform` realm. Put
that user's immutable ID in `PLATFORM_BOOTSTRAP_SUBJECT` and start the API. Remove
the setting after the first platform-admin grant exists. Follow
[Identity and access](identity-and-access.md) for the complete procedure.

## Verify

```bash
docker compose ps
curl --fail-with-body http://127.0.0.1:8000/healthz
curl --fail-with-body http://127.0.0.1:8000/readyz
kubectl --kubeconfig .runtime/admin.kubeconfig get pods -A
python3 scripts/smoke.py
```

The smoke test retains its project. `/healthz` proves only API process health and
`/readyz` checks PostgreSQL plus Kubernetes connectivity; neither proves every
workload. Use [platform acceptance](validation/acceptance.md) for the broader
suite and [lifecycle](lifecycle.md) for stop, restart, recreation, and cleanup.
