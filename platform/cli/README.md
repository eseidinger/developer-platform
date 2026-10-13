# Developer Platform CLI

This source-adjacent README provides the minimal development example. The
canonical user documentation is the [CLI guide](../../docs/developers/cli.md);
implementation ownership is in the [maintainer guide](../../docs/maintainers/cli.md).

`devplat` is the command-line client for the Developer Platform API. It supports
CI deployments and project administration, including hosted application access.
Use `devplat --help` and `devplat access --help` to inspect commands.

Install an editable development copy:

```bash
python3 -m pip install -e 'platform/cli[dev]'
```

Set the values returned when the deployment credential was created. Keep the secret
in the CI system's protected environment and disable shell tracing around this step:

```bash
export PLATFORM_API_URL=https://platform.example
export PLATFORM_TOKEN_ENDPOINT=https://identity.example/realms/platform/protocol/openid-connect/token
export PLATFORM_CLIENT_ID='...'
export PLATFORM_CLIENT_SECRET='...'
devplat deploy apply --project hello --file examples/project.json --wait
```

`PLATFORM_ACCESS_TOKEN` may be used instead of the deployment-credential variables
for a short-lived, externally obtained token. The CLI never persists either form of
authentication material. Deployment credentials authorize deployment and observation
only; access administration requires a human project-administrator login or an
externally supplied administrator token. See the [CLI guide](../../docs/developers/cli.md)
for profiles, login, access commands, and versioned updates.
