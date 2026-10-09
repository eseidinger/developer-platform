# CLI guide

Status: current. Last reviewed October 9, 2026.

`devplat` is the command-line client for the Developer Platform API. Install it
from the repository for development:

```bash
python3 -m pip install -e 'platform/cli[dev]'
```

Configure either a short-lived access token or a complete deployment-credential
set. The CLI never persists either form of authentication material.

```bash
export PLATFORM_API_URL=https://platform.example
export PLATFORM_TOKEN_ENDPOINT=https://identity.example/realms/platform/protocol/openid-connect/token
export PLATFORM_CLIENT_ID='...'
export PLATFORM_CLIENT_SECRET='...'
devplat deploy apply --project hello --file application.json --wait
```

For an interactive token, set only `PLATFORM_API_URL` and
`PLATFORM_ACCESS_TOKEN`. Do not mix incomplete deployment-credential variables
with an access token.

Use `--if-match REVISION` to protect an update from overwriting a newer revision,
and `--output json` for automation. A wait timeout does not cancel the server-side
operation; retain its ID and inspect it through the API or UI.

See [Getting started](getting-started.md) for a complete deployment and
[CI deployment](ci-deployment.md) for protected automation variables. CLI
implementation and tests are documented in the [maintainer guide](../maintainers/cli.md).
