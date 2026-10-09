# Deploy from CI

Status: current supported workflow. Last reviewed October 9, 2026.

This guide starts after a platform administrator has created a project-scoped
deployment credential. For the interactive first deployment, begin with
[Getting started](getting-started.md).

## CI workflow

Store all four variables as protected CI secrets or variables, with the client
secret always secret. This GitHub Actions job illustrates the minimum deployment
step; it deliberately never echoes credential values.

```yaml
deploy:
  runs-on: ubuntu-latest
  environment: production
  steps:
    - uses: actions/checkout@v7
    - uses: actions/setup-python@v7
      with:
        python-version: "3.12"
    - run: python3 -m pip install developer-platform-cli
    - run: devplat deploy apply --project orders --file application.json --wait --output json
      env:
        PLATFORM_API_URL: ${{ vars.PLATFORM_API_URL }}
        PLATFORM_TOKEN_ENDPOINT: ${{ vars.PLATFORM_TOKEN_ENDPOINT }}
        PLATFORM_CLIENT_ID: ${{ secrets.PLATFORM_CLIENT_ID }}
        PLATFORM_CLIENT_SECRET: ${{ secrets.PLATFORM_CLIENT_SECRET }}
```

Limit the credential to its project and rotate or revoke it through the platform
when a repository, environment, or team member no longer needs deployment access.
Avoid shell tracing (`set -x`) around any command that handles credentials.
