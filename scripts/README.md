# Repository scripts

Run commands from the repository root. Install Python dependencies using the
root `requirements.txt`; API-dependent scripts can also use
`uv run --project platform/app`.

The main entry points remain `scripts/init.py`, `scripts/up.sh`, and
`scripts/down.sh`. Local setup and Ansible share configuration validation and
controlled deployment; see the
[configuration and deployment guide](../docs/operators/configuration-and-deployment.md).

## Operational commands

| Directory     | Purpose                                                  |
| ------------- | -------------------------------------------------------- |
| `setup/`      | Prepare tools, infrastructure, and configuration.        |
| `generate/`   | Generate API contracts and monitoring dashboards.        |
| `checks/`     | Validate repository documents and network configuration. |
| `operations/` | Deploy the platform and inspect operational state.       |
| `release/`    | Prepare release workflows.                               |
| `internal/`   | Shared configuration and bootstrap implementation.       |

## Tests

All script-based tests live under [`tests/`](tests/README.md). Choose by the
execution environment, rather than whether the author called a script a check,
verification, acceptance test, or drill:

| Directory           | What it needs                                    |
| ------------------- | ------------------------------------------------ |
| `tests/unit/`       | Offline mocks and temporary files.               |
| `tests/components/` | Component dependencies and integration fixtures. |
| `tests/platform/`   | A configured, running platform.                  |
| `tests/support/`    | Shared test helpers; not operator entry points.  |

Component checks are grouped by `stores`, `observability`, and `ai`. They may
start disposable Docker services or need a test database. The AI corpus
evaluation is an explicitly invoked benchmark that calls the configured model;
it is not part of the routine regression suite. Cross-store bound application
commands live under `scripts/tests/platform/`. Reusable runner logic lives in
[`tests/platform/`](../tests/README.md), separate from the platform application.
Platform tests can change or
retire resources; the interruption and outage drills also affect shared
services. Read the specific script and the
[acceptance guide](../docs/operators/validation/acceptance.md) before execution.
The directory name alone does not authorize running a test.

Examples:

```bash
python3 scripts/generate/generate-dashboards.py --check
python3 scripts/checks/check-doc-links.py
python3 scripts/checks/check-network-addresses.py --validate-only
python3 -m unittest discover -s scripts/tests/unit -v
uv run --project platform/app python \
  scripts/tests/platform/check-hosted-access.py plan
uv run --project platform/app python \
  scripts/tests/components/stores/verify-named-postgres.py
```

The former `verify/`, `acceptance/`, `drills/`, and `fixtures/` directories have
been consolidated into this layout. Python test helpers are imported through
`scripts.tests.support`; production helpers remain in `scripts.internal`. Update
imports, root-relative paths, CI, and documentation whenever moving a script.
Keep `__init__.py` files in importable helper packages.
