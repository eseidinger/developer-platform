# Ansible automation

Use the [remote installation guide](../docs/operators/install-remote.md) for the
canonical deployment sequence. Run Ansible commands from the repository root;
`ansible.cfg` locates the shared inventory filter plugin for every playbook.

## Deployment and operations

- **`deploy.yml`**: the primary installation entry point. Prepare the host,
  transfer sources, and invoke the shared configuration/deployment scripts.
- **`operations/install-human-database-access.yml`**: install the optional
  restricted SSH tunnel.
- **`operations/bootstrap-platform-test-runner.yml`**: create the expiring
  credential used by platform tests.
- **`operations/revoke-platform-test-runner.yml`**: revoke that credential and
  wait for provider cleanup.
- **`operations/retire-platform-project.yml`**: explicitly retire a selected
  project and verify cleanup.

Local operators and Ansible use `scripts/setup/configure-platform.py` and
`scripts/operations/deploy-platform.py`. Shared configuration rules live in
`scripts/internal`; see the
[configuration and deployment
guide](../docs/operators/configuration-and-deployment.md).

## Tests

All tests live under [`tests/`](tests/README.md), divided by their execution
requirements:

- **`tests/unit/`** contains Python tests for inventory rendering, command
  arguments, ordering, and cleanup contracts. They use offline fixtures and
  temporary local playbooks.
- **`tests/platform/`** contains playbooks against an installed platform: role
  and CI credentials, application components, hosted/human access, credential
  expiry, capacity, egress, outages, failure signals, and data-aware rollback.
  Hosted/human access default to offline plans; other playbooks may change
  resources immediately or deliberately interrupt shared services.

A `test-` filename does not make a playbook safe to run on an arbitrary host.
Read the [platform test and drill reference](docs/acceptance-and-drills.md)
before execution. Credential setup is documented in the
[test-runner guide](docs/test-runner.md).

## Implementation and configuration

- `tasks/deploy/`: imported deployment phases.
- `tasks/tests/`: imported platform-test scenarios, grouped by responsibility.
- `templates/`: installed SSH/systemd/Docker configuration and installation
  evidence fragments.
- `filter_plugins/`: the shared configuration rules' Ansible adapter.
- `docs/`: inventory, deployment, credential, and test procedures.
- `inventory.example.yml` and `human-bootstrap-vars.example.yml`: configuration
  examples, not playbooks. Keep their local counterparts private.

Files under `tasks/` are task fragments, not standalone playbooks. Preserve
registered variables, task order, `block`/`always` cleanup, `no_log`, and
privilege boundaries when changing them. Operational and platform-test playbooks
previously lived at the root; their commands now use the directories above.

## Offline checks

Install the root development requirements, then run from the repository root:

```bash
ruff check ansible
ruff format --check ansible
pymarkdown scan --recurse ansible
mdformat --check ansible
uv run --project platform/app --with 'ansible-core>=2.16,<2.22' \
  --with pyyaml python -m unittest discover -s ansible/tests/unit -v
ansible-playbook -i ansible/inventory.example.yml \
  ansible/deploy.yml --syntax-check
```

Run `yamllint` on versioned YAML and `ansible-lint --offline` on `deploy.yml`,
`operations/*.yml`, and `tests/platform/*.yml`. Syntax checking does not execute
any deployment or test. Detailed deployment behavior lives in the
[deployment reference](docs/deployment.md); optional settings are described in
[inventory options](docs/inventory-options.md).
