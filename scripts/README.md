# Repository scripts

Run scripts from the repository root. Install Python dependencies using the root
`requirements.txt`; API-dependent scripts can also use
`uv run --project platform/app`.

The main entry points remain `scripts/init.py`, `scripts/up.sh`, and
`scripts/down.sh`. Configuration and controlled deployment are shared with
Ansible through `setup/configure-platform.py` and
`operations/deploy-platform.py`. See the
[shared configuration and deployment guide](../docs/operators/configuration-and-deployment.md).

| Directory               | Purpose                                          |
| ----------------------- | ------------------------------------------------ |
| `setup/`                | Tools, infrastructure, and configuration.        |
| `generate/`             | API contracts and monitoring dashboards.         |
| `checks/`               | Documentation, networks, and security checks.    |
| `verify/stores/`        | Storage and recovery verification.               |
| `verify/observability/` | Metrics, logs, and traces verification.          |
| `verify/ai/`            | AI guards, history, diagnostics, and evaluation. |
| `verify/applications/`  | Application flow verification.                   |
| `acceptance/`           | Acceptance plans, checks, and smoke tests.       |
| `drills/`               | Explicitly scoped live lab exercises.            |
| `fixtures/`             | Shared disposable verification fixtures.         |
| `operations/`           | Controlled deployment and operator inspection.   |
| `release/`              | Release workflow helpers.                        |
| `internal/`             | Shared configuration and bootstrap logic.        |
| `tests/`                | Offline configuration and deployment tests.      |

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
direct file invocation works. Keep repository-root paths relative to each
script's location when adding or moving files.
