# Platform operations

These playbooks manage optional access, test credentials, or project lifecycle.
They are independent of normal platform installation through
`ansible/deploy.yml`. Run commands from the repository root so `ansible.cfg`
supplies the shared filter plugin path.

- `install-human-database-access.yml`: install the optional dedicated SSH tunnel
  service. The default listener is loopback; configure a deliberately selected
  management address and firewall before exposing it remotely.
- `bootstrap-platform-test-runner.yml`: create an expiring acceptance runner and
  save its credential privately on the controller.
- `revoke-platform-test-runner.yml`: revoke the selected runner and wait for
  identity-provider cleanup.
- `retire-platform-project.yml`: retire a deliberately selected project and
  verify its cleanup; existing projects require exact confirmation.

See [test-runner credentials](../docs/test-runner.md),
[human database access](../../docs/developers/database-access.md), and the
[Ansible directory guide](../README.md) for prerequisites. These operations
change real service configuration or catalog state; they are not offline tests.
