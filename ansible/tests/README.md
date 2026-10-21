# Ansible tests

There are two execution environments:

- **`unit/`**: Python contract tests. They validate source files and run
  temporary local Ansible tasks; they do not deploy the platform.
- **`platform/`**: Ansible playbooks that inspect or exercise an installed
  platform. Live runs create credentials/projects, change policy, or interrupt
  shared services according to the selected scenario.

From the repository root:

```bash
python3 -m unittest discover -s ansible/tests/unit -v
ansible-playbook -i ansible/inventory.example.yml \
  ansible/tests/platform/test-platform.yml --syntax-check
```

The platform playbooks cover:

| Playbook suffix            | Scenario                                  |
| -------------------------- | ----------------------------------------- |
| `base`                     | Roles, deployment, and credentials.       |
| `ci-credential`            | CI credentials and revocation.            |
| `components`               | Services, jobs, updates, and retirement.  |
| `hosted-access`            | Hosted authorization; defaults to plan.   |
| `human-database-access`    | SQL tunnel and grants; defaults to plan.  |
| `capacity-admission`       | Resource-pressure rejection and recovery. |
| `egress-policy`            | Allowed and denied outbound connections.  |
| `failure-signals`          | Application and monitoring failures.      |
| `identity-provider-outage` | Keycloak outage and credential cleanup.   |
| `postgres-outage`          | Database outage and recovery.             |
| `rollback-data`            | Rollback with retained data/secrets.      |
| `expiry`                   | Before/after expiry checks.               |

Suffixes belong to `test-platform-<suffix>.yml`, except `base`, which is
`test-platform.yml`, and `expiry`, which is
`verify-platform-test-runner-expiry.yml`. Do not run this directory as an
automatic batch. Outage/capacity/failure drills require an approved lab scope
and explicit acknowledgements. Details and cleanup contracts are in the
[platform test and drill reference](../docs/acceptance-and-drills.md).

Test-runner creation/revocation and deliberate project retirement are
operational actions under [`operations/`](../operations/README.md), separate
from tests. Imported test implementation lives under `ansible/tasks/tests/`.
