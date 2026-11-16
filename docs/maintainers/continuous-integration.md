# Continuous integration

Status: current. Last reviewed November 16, 2026.

The [CI workflow](../../.github/workflows/ci.yaml) coordinates reusable validation,
API, UI, telemetry, store and production-image workflows. It runs on pull
requests, pushes to `main` and `v*` tags, manual invocation and a daily
03:17 UTC schedule. Component jobs use disposable local dependencies; they do
not contact or deploy an installed platform.

## Required checks and releases

Configure branch protection to require `Required CI`, the final aggregate job.
It rejects failed or cancelled dependencies and unexpected skips. Markdown-only
changes can skip runtime/component jobs only after successful change selection.
Changes to shared code, tests, dependency locks, workflows and configuration run
all components. Tags, schedules and manual runs always run the full suite.
Machine-readable contracts under `docs/` also trigger the full suite.

The [platform-cli repository](https://github.com/eseidinger/platform-cli)
builds and publishes the CLI in its own workflow. A `vMAJOR.MINOR.PATCH` tag
must match its `pyproject.toml`. That workflow tests the source and installed
wheel before the protected `pypi` job publishes the tested artifacts.

The hosted-access fixture has a separate, narrowly triggered workflow and
protected Docker Hub release environment. It publishes a neutral test
application, not the platform, and does not run installed-platform acceptance.

## Test layers

| Layer          | Checks                                           |
| -------------- | ------------------------------------------------ |
| Static quality | Source linters, Compose and Ansible syntax       |
| API            | SQL and identity checks on Python 3.12/3.14      |
| Lifecycle      | Retire/restore/purge with real PostgreSQL stores |
| UI             | Quality, unit tests, build and browser fixtures  |
| Components     | TLS, telemetry, stores, SSO and backup/recovery  |
| Image          | Actual Dockerfile, runtime and bundled assets    |

Required API tests use `--fail-on-skip` with `tests.support.pytest_ci`. Missing
SQL or identity-provider prerequisites therefore fail their CI phase rather
than silently reducing coverage. The API test group is excluded from the
production image. Backup tests explicitly enable a real encrypted local restic
repository round trip.

Component jobs run independently with bounded timeouts. Logging uses project
UUID labels and tenant-aware Loki reads. Tracing exercises the production router
with its real read-only PostgreSQL views, Alloy gzip transport and multitenant
Tempo; synthetic provider responses avoid model requests. Store checks include
all advertised PostgreSQL extensions and real empty-server backup restoration.
Production platform and PostgreSQL image builds retain separate BuildKit caches
in GitHub Actions; a cold PostgreSQL extension build can take about 20 minutes.

Browser scenarios use synthetic API fixtures and authentication contexts. API
lifecycle integration uses fixture audit writes, a Kubernetes double and signed
receipts at the privileged host boundary. Native component and host tests cover
those dependencies separately; these checks are not evidence of a complete
installed platform journey. Keep live API/CLI/browser acceptance and outage
drills under the explicit operator procedures in the
[testing requirements](testing-requirements.md) and
[acceptance guide](../operators/validation/acceptance.md).

Failures retain component logs, API JUnit results and browser screenshots/traces
where available. Evidence contains synthetic fixture data and expires after
seven days. Historical ADRs and plans remain unchanged and are excluded from
current-source formatting checks.

## Reproducing checks

Install root `requirements.txt`, then run
`python3 scripts/checks/check-quality.py` for all tracked current source. An
optional `--base COMMIT` limits a local scan to changed files. The workflow also
runs actionlint with ShellCheck for embedded shell scripts.

Use the commands and prerequisites in the reusable workflows for component
checks; several require the local Linux Docker daemon, browser tooling or
restic. Never substitute an installed-platform database for a disposable test
DSN. The [script test guide](../../scripts/tests/README.md) describes fixture and
live-runner boundaries.
