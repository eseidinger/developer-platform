# Ansible tests

There are two execution environments:

- **`unit/`**: Python contract tests. They validate source files and run
  temporary local Ansible tasks; they do not deploy the platform.
- **`platform/`**: Ansible playbooks that inspect or exercise an installed
  platform. Live runs create credentials/projects, change policy, or interrupt
  shared services according to the selected scenario.

From the repository root:

```bash
uv run --project platform/app --with 'ansible-core>=2.16,<2.22' \
  --with pyyaml python -m unittest discover -s ansible/tests/unit -v
ansible-playbook -i ansible/inventory.example.yml \
  ansible/tests/platform/test-platform.yml --syntax-check
```

The platform playbooks cover:

| Playbook suffix            | Scenario                                    |
| -------------------------- | ------------------------------------------- |
| `base`                     | Roles, deployment, and credentials.         |
| `components`               | Services, jobs, updates, and retirement.    |
| `hosted-access`            | Hosted authorization; defaults to plan.     |
| `human-database-access`    | SQL tunnel and grants; defaults to plan.    |
| `capacity-admission`       | Resource-pressure rejection and recovery.   |
| `egress-policy`            | Allowed and denied outbound connections.    |
| `failure-signals`          | Application and monitoring failures.        |
| `identity-provider-outage` | Keycloak outage and credential cleanup.     |
| `postgres-outage`          | Control-plane catalog outage and recovery.  |
| `rollback-data`            | Rollback with retained data/secrets.        |
| `expiry`                   | Expiry boundary with an unexpired held JWT. |

Suffixes belong to `test-platform-<suffix>.yml`, except `base`, which is
`test-platform.yml`, and `expiry`, which is
`verify-platform-test-runner-expiry.yml`. Do not run this directory as an
automatic batch. Outage/capacity/failure drills require an approved lab scope
and explicit acknowledgements. Details and cleanup contracts are in the
[platform test and drill reference](../docs/acceptance-and-drills.md).

Test-runner creation/revocation and deliberate project retirement are
operational actions under [`operations/`](../operations/README.md), separate
from tests. Imported test implementation lives under `ansible/tasks/tests/`.

## Ownership and cleanup

The main platform suite includes project-scoped CI deployment, cross-project
and administration denial, secret-mutation denial, rotation, and revocation.
The former standalone CI-credential playbook has been consolidated into it.

API suites register successful project creation responses. Their `always`
blocks invoke the shared cleanup helper with those responses; a name alone
never establishes ownership. Partial creation cleans only confirmed fixtures.
Cleanup refreshes retirement scopes, waits for provider revocation, attempts
remaining fixtures after an error, and fails the final result if incomplete.
Named-store data remains retained; tests do not purge it.

Shared environment/service restoration stays in the relevant playbook's
`always` block. Restoration failures are recorded while remaining cleanup is
attempted, then cause the final assertion to fail. Offline tests verify these
boundaries and exercise cleanup failures without contacting a platform.

The rollback-schema contract requires application dependencies and no longer
silently skips when they are missing. CI runs it in the application environment.
Release-workflow tests live under `scripts/tests/unit/`.
