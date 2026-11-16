# CLI maintenance

Status: active implementation.

The Python `devplat` package is a thin client over the versioned Platform API.
It must not reproduce server authorization. Environment tokens and machine
secrets remain in memory; human renewable sessions use the OS keyring bound to
the selected profile, issuer, client ID and subject. Standard output is reserved
for requested results so machine-readable output remains safe for CI.

Run from the [platform-cli repository](https://github.com/eseidinger/platform-cli)
root:

```bash
python3 -m pip install -e '.[dev]'
python3 scripts/generate-cli-contract.py \
  --source ../developer-platform/docs/api/openapi.json --check
devplat contract check --output json
python3 -m pytest tests
```

See the [CLI README](https://github.com/eseidinger/platform-cli/blob/main/README.md)
for its minimal runtime example and the
[implementation plan](../history/plans/cli.md) for active increments. Stable
commands and authentication behavior belong in the
[developer CLI guide](../developers/cli.md), not only in the plan.
