# Repository scripts

Run scripts from the repository root. Install Python dependencies using the root
`requirements.txt`; API-dependent scripts can also use `uv run --project platform/app`.

The main entry points remain `scripts/init.py`, `scripts/up.sh`, and
`scripts/down.sh`.

| Directory | Purpose |
| --- | --- |
| `setup/` | Install local tools and prepare platform infrastructure and configuration. |
| `generate/` | Generate or check API contracts and monitoring dashboards. |
| `checks/` | Check documentation, network settings, and platform security state. |
| `verify/stores/` | Verify storage providers, catalogs, consoles, TLS, and recovery. |
| `verify/observability/` | Verify monitoring, metrics, logs, and trace pipelines. |
| `verify/ai/` | Verify AI approval guards, history, diagnostics, and model evaluation. |
| `verify/applications/` | Verify application flows across platform components. |
| `acceptance/` | Run acceptance plans, scoped acceptance checks, and stack smoke checks. |
| `drills/` | Exercise configuration, secrets, logs, authorization, and retirement on a live lab. |
| `fixtures/` | Shared disposable fixture modules imported by verification scripts. |
| `operations/` | Operator inspection tools, including AI trace review. |
| `release/` | Release workflow helpers. |
| `internal/` | Shared configuration helpers and bootstrap commands. |

Examples:

```bash
python3 scripts/generate/generate-dashboards.py --check
python3 scripts/generate/generate-cli-contract.py --check
python3 scripts/checks/check-doc-links.py
python3 scripts/checks/check-network-addresses.py --validate-only
uv run --project platform/app python scripts/acceptance/check-hosted-access.py plan
uv run --project platform/app python scripts/verify/stores/verify-named-postgres.py
```

Read a script's prerequisites before execution. Verification scripts may start
temporary Docker services, contact configured providers, or require database
access. Acceptance scripts and live drills can change lab resources; follow the
[acceptance guide](../docs/operators/validation/acceptance.md).

Python helpers are imported through `scripts.internal` and `scripts.fixtures`.
Scripts that use these packages add the repository root to their import path so
direct file invocation works. Keep repository-root paths relative to each script's
location when adding or moving files.
