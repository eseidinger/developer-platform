# Identity services

`compose.yaml` defines Keycloak and its two one-shot initializers. Run Compose
from the repository root so shared services, networks, and volumes are included.

- `init-database.sh` waits for PostgreSQL, creates the restricted identity role
  and database when absent, and refreshes the role password on later runs.
- `realm-platform.json` supplies the initial realm imported by Keycloak.
- `init-realm.sh` waits for administrator authentication, reconciles the portal
  and console clients, and grants the credential provisioner its existing realm
  management roles. It refreshes configured secrets without deleting clients.
- `tests/` exercises initialization with local CLI stand-ins, including existing
  installations and failure handling. It makes no live service calls.

Compose mounts the scripts read-only and runs them with `/bin/sh`. They use
administrator credentials only for initialization; do not enable shell tracing
or log command arguments containing secrets.

Run these checks from the repository root:

```bash
yamllint infrastructure/identity
shellcheck infrastructure/identity/*.sh
sh -n infrastructure/identity/init-database.sh
sh -n infrastructure/identity/init-realm.sh
python3 -m unittest discover -s infrastructure/identity/tests -v
docker compose --profile '*' config --quiet
```
