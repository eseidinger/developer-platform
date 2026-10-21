# Platform infrastructure

This directory owns the supporting services and cluster configuration used by
the platform. The root `compose.yaml` includes the service definitions here; run
Compose commands from the repository root.

- `identity/`: Keycloak services, initialization, and the platform realm.
- `persistence/`: PostgreSQL and optional store services, console configuration,
  reviewed image builds, and compatibility evidence.
- `kubernetes/`: cluster service accounts, RBAC, and metrics manifests.
- `monitoring/`: collectors, backends, rules, and generated dashboards. See the
  [monitoring directory guide](monitoring/README.md).
- `proxy/`: edge routing and certificate admission through Caddy.

Application/control-plane code remains in `platform/`. Cross-platform backup,
recovery, maintenance, and external availability procedures remain in
[`operations/`](../operations/README.md). Ansible deploys the infrastructure as
part of the [platform checkout](../ansible/README.md).

Identity and persistence previously lived at the repository root. Current
deployment archives capture them through this directory. Backup/recovery tools
also support bundles made with the earlier layout.

Validate the combined configuration without starting services:

```bash
docker compose --profile '*' config --quiet
python3 scripts/checks/check-doc-links.py
```
