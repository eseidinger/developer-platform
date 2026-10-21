# Ansible automation

Use the [remote installation guide](../docs/operators/install-remote.md) for the
canonical deployment sequence. This directory owns the platform playbooks,
validation filters, configuration templates, and offline contract tests.

## Structure

- Top-level playbooks are stable public entry points for operators and
  workflows.
- `tasks/deploy/` separates preflight checks, host setup, source transfer,
  private configuration, tools, monitoring storage, maintenance checks, startup,
  and installation records.
- `tasks/acceptance/` groups platform and component acceptance phases.
- `tasks/drills/` groups capacity, failure-signal, and data-rollback phases.
- `templates/` contains installed SSH/systemd/Docker configuration and the shell
  fragments used to record installation evidence.
- `filter_plugins/platform_inventory.py` validates and renders non-secret
  inventory settings. Keep the plugin beside the public playbooks so automatic
  Ansible discovery continues to work.
- `tests/` checks inventory rendering, task ordering, command arguments, and
  cleanup contracts without deploying the platform.
- `docs/` contains the detailed variable, credential, and operational
  references.

The entry points use static task imports. Registered variables remain available
across phases, and each original `block`/`always` boundary encloses its imported
steps. Preserve task order, delegation, `no_log`, privilege settings, and
cleanup when changing these files.

## Deployment and access

- `deploy.yml`: prepare the host, transfer the checkout, and reconcile services.
- `install-human-database-access.yml`: install the optional restricted SSH
  tunnel.
- [Deployment reference](docs/deployment.md): prerequisites, source transfer,
  reapplication, and deployment outage behavior.
- [Inventory options](docs/inventory-options.md): defaults and explicitly
  managed non-secret settings, store/network selection, and tracing.

## Credentials and acceptance

- `bootstrap-platform-test-runner.yml`, `revoke-platform-test-runner.yml`, and
  `verify-platform-test-runner-expiry.yml`: manage the scoped acceptance runner.
  See [test-runner credentials](docs/test-runner.md).
- `test-platform.yml`, `test-platform-ci-credential.yml`, and
  `test-platform-components.yml`: exercise platform/component contracts using
  disposable projects and protected runner credentials.
- `test-platform-hosted-access.yml` and
  `test-platform-human-database-access.yml`: default to offline plans; live
  commands require a separately confirmed scope and protected operator session.
- `retire-platform-project.yml`: explicitly retire a selected project.

## Operational drills

Capacity, egress, PostgreSQL outage, identity-provider outage, failure-signal,
and rollback-data playbooks live beside the entry points for compatibility. Read
the [acceptance and drill reference](docs/acceptance-and-drills.md) before
execution. Shared-service outage drills require explicit approval and belong in
protected operator workflows, outside routine pull-request CI.

## Local checks

Install the root `requirements.txt`, then run these from the repository root:

```bash
ruff check ansible
ruff format --check ansible
pymarkdown scan --recurse ansible
mdformat --check ansible
python3 -m unittest discover -s ansible/tests -v
ansible-playbook -i ansible/inventory.example.yml \
  ansible/deploy.yml --syntax-check
```

Run `yamllint` against the versioned examples, playbooks, and task files, and
`ansible-lint --offline` against the top-level playbooks. Keep local
`inventory.yml` and `human-bootstrap-vars.yml` private; use the example
inventory for syntax checks. Syntax checking does not execute deployment or
drill tasks.
