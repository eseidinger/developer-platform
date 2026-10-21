# Shared test infrastructure

This directory contains reusable test infrastructure outside the application
packages. Operator commands remain under `scripts/tests/platform/`.

- `platform/`: platform scenario implementations, CLI validation, and cleanup.
- `platform/unit/`: offline regression tests for those runners. These use mocks,
  temporary files, and local HTTP fixtures; they never deploy a platform.
- `fixtures/hosted-application/`: the neutral hosted application, its Dockerfile,
  and its own dependency file. Its build context excludes the runner code.
- `support/`: synthetic policy and identity data shared by API and runner tests.

API unit tests remain under `platform/app/tests/`. Script regression tests live
under `scripts/tests/unit/`, and Ansible contract tests under
`ansible/tests/unit/`. The repository root is on the Python import path so
runners use the explicit `tests.platform` package.

## Offline checks

From the repository root:

```bash
uv run --project platform/app python -m unittest discover \
  -s tests/platform/unit -v
uv run --project platform/app python -m unittest discover \
  -s scripts/tests/unit -v
uv run --project platform/app python -m unittest discover \
  -s platform/app/tests -v
```

Optional PostgreSQL and identity-provider integration checks require the
explicit test environment variables declared in CI. A skipped integration check
does not establish deployed behavior.

## Hosted application fixture

Build only the fixture directory:

```bash
docker build -t hosted-access-fixture:test tests/fixtures/hosted-application
```

The fixture is deliberately free of authorization logic. It contains synthetic
state only; the platform supplies authentication and authorization. Never use
it for real application data. Publishing its image and running a live scenario
are separate actions.

## Running-platform commands

See the [script test guide](../scripts/tests/README.md) for prerequisites and
explicit `plan`/`run` commands. Moving code here does not authorize live drills.
