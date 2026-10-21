# CLI maintenance

Status: active implementation.

The Python `devplat` package is a thin client over the versioned Platform API. It
must not reproduce server authorization. Environment tokens and machine secrets
remain in memory; human renewable sessions use the OS keyring bound to the selected
profile, issuer, client ID and subject. Standard
output is reserved for requested results so machine-readable output remains safe
for CI.

Run from the repository root:

```bash
python3 -m pip install -e 'platform/cli[dev]'
python3 scripts/generate/generate-cli-contract.py --check
devplat contract check --output json
python3 -m pytest platform/cli/tests
```

See the source-adjacent [CLI README](../../platform/cli/README.md) for its minimal
runtime example and the [implementation plan](delivery/plans/cli.md) for active
increments. Stable commands and authentication behavior belong in the
[developer CLI guide](../developers/cli.md), not only in the plan.
