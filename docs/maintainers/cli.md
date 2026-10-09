# CLI maintenance

Status: active implementation.

The Python `devplat` package is a thin client over the versioned Platform API. It
must not reproduce server authorization or persist tokens and secrets. Standard
output is reserved for requested results so machine-readable output remains safe
for CI.

Run from the repository root:

```bash
python3 -m pip install -e 'platform/cli[dev]'
```

See the source-adjacent [CLI README](../../platform/cli/README.md) for its minimal
runtime example and the [implementation plan](delivery/plans/cli.md) for active
increments. Stable commands and authentication behavior belong in the
[developer CLI guide](../developers/cli.md), not only in the plan.
