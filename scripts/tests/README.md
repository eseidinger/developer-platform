# Script tests

Choose tests by execution environment. A `check-` or `verify-` prefix does not
promise that a command is read-only.

- **`unit/`**: offline configuration and deployment contracts; run in CI.
- **`components/stores/`**: disposable provider, access, TLS, console, and recovery
  fixtures; run in CI.
- **`components/observability/`**: disposable metric, log, trace, and dashboard
  fixtures; run in CI.
- **`components/ai/`**: SQL and driver checks in CI; model evaluation is an
  explicitly invoked benchmark.
- **`platform/`**: explicit scenarios against a running lab.
- **`support/`**: importable fixtures called by component tests.

API tests remain under `platform/app/tests`; Ansible tests have the same
execution-environment distinction under [`ansible/tests/`](../../ansible/tests/README.md).

## Offline regression tests

```bash
python3 -m unittest discover -s scripts/tests/unit -v
uv run --project platform/app python -m unittest discover \
  -s platform/app/tests -p test_lifecycle_acceptance.py -v
uv run --project platform/app python -m unittest discover \
  -s platform/app/tests -p test_script_fixtures.py -v
```

These use mocks and temporary files. They never deploy the platform.
Ansible fixture cleanup, timed expiry evidence, and release-workflow checks
also have offline regression tests under `unit/`. Their shared implementations
live in `support/`; live Ansible callers pass credentials over private stdin.
CI also checks deployment, operations, and platform-test Ansible playbooks.

## Disposable component tests

Store checks cover different contracts: production Compose wiring, provider
lifecycle, OpenSearch TLS, Neo4j catalog behavior, and network recreation.
Observability checks validate actual collector/storage behavior. Keep these
separate so a focused failure can be reproduced without running every provider.
Some recovery, analytics, and browser paths require the flags and tools declared
in `.github/workflows/named-stores.yaml` and `http-stores.yaml`.

AI approval and portal-history checks can run together against an isolated
PostgreSQL test server:

```bash
# Explicitly select a disposable server where this user may create databases.
export AI_FIXTURE_TEST_DSN='host=127.0.0.1 port=5432 user=postgres dbname=postgres'
uv run --project platform/app python scripts/tests/components/ai/verify-ai-sql.py
uv run --project platform/app --with sqlalchemy==2.0.46 python \
  scripts/tests/components/ai/verify-ai-database-diagnostics.py
```

The SQL runner creates a uniquely named database, initializes the production AI
schema, executes both rollback-only fixtures, and drops that database on exit.
The driver check is offline. Neither calls a model. `evaluate-ai.py` remains an
optional provider-dependent benchmark, with potential model charges; it is not
part of routine CI.

## Smoke and lifecycle checks

Both runners require `plan` or `run`; importing them performs no operations.
`plan` does not read credentials or contact services. Run these on the platform
host, using that installation's settings, kubeconfigs, and Compose services.

The smoke runner checks the legacy flat deployment compatibility contract:
unauthenticated denial, repeat provisioning, readiness, and public HTTP routing.
Use a digest-pinned `hashicorp/http-echo` image listening on port 5678. The full
lifecycle runner uses the digest-pinned neutral image built from
[`platform/acceptance/Dockerfile.fixture`](../../platform/acceptance/Dockerfile.fixture)
and listening on port 8080. Protected `v1alpha2` application behavior remains in
the [hosted-access harness](../../docs/operators/validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness).

```bash
# Set this to the appropriate reviewed image reference ending @sha256:<digest>.
export SMOKE_FIXTURE_IMAGE='hashicorp/http-echo@sha256:<reviewed-digest>'
uv run --project platform/app python scripts/tests/platform/smoke.py plan \
  --run-id 0123456789ab --fixture-image "$SMOKE_FIXTURE_IMAGE"

# Explicit live execution; use a fresh 12-character hexadecimal run id each time.
uv run --project platform/app python scripts/tests/platform/smoke.py run \
  --run-id 0123456789ab --fixture-image "$SMOKE_FIXTURE_IMAGE" \
  --confirm-environment http://127.0.0.1:8000 \
  --operator-token-file /path/to/private-operator-session.json

uv run --project platform/app python \
  scripts/tests/platform/check-lifecycle.py plan \
  --run-id abcdef012345 --fixture-image "$LIFECYCLE_FIXTURE_IMAGE"
uv run --project platform/app python \
  scripts/tests/platform/check-lifecycle.py run \
  --run-id abcdef012345 --fixture-image "$LIFECYCLE_FIXTURE_IMAGE" \
  --confirm-environment http://127.0.0.1:8000 \
  --operator-token-file /path/to/private-operator-session.json \
  --other-token-file /path/to/private-ungranted-user-token
```

The operator session is the private JSON file used by the hosted-access harness,
containing `access_token`, `refresh_token`, and `client_id` for a renewable human
administrator session. The other file contains a bearer token for an authenticated
user with no project or platform grants. Both files must have private permissions
(for example, mode `0600`). Full lifecycle execution requires both identities;
authorization and audit assertions cannot silently skip themselves.

The full suite consolidates the former `config_drill.py`, `secret_drill.py`,
`log_drill.py`, `retirement_drill.py`, and `access_audit_drill.py` commands:

- Configuration validation, stale-revision rejection, replacement, removal,
  clearing, activation, and drift.
- Write-only secrets, direct pod adoption, rotation, revert, confirmation,
  revocation of previous values, and response/log redaction.
- Failed-pod logs with attribution, ordering, separate lines, and redaction.
- Ungranted-user denial, unauthenticated denial, and required audit records.
- Controller namespace confinement, stale retirement scope rejection, namespace
  removal, and retained database, role, and inventory.

Each run refuses an existing project and owns only `lc-<run-id>`. Cleanup attempts
retirement after success, assertion failure, or interruption; SQL data and catalog
remain retained. It never purges a database. Private reports live under
`.runtime/application-lifecycle/<run-id>/report.json`. A lost create response or
failed cleanup produces a failed report requiring manual review; it does not
adopt a project based solely on its name. Historical evidence retains the old
command names at the recorded commits and does not prove the new runner live.

## Other running-platform scenarios

Keep hosted access, human database access, data preservation, isolation, and
interrupted provisioning separate: they exercise distinct platform guarantees.
Use their `plan` commands and consult the
[acceptance procedure](../../docs/operators/validation/acceptance.md).
`interrupted_provisioning.py` interrupts shared cluster/API services. Never run
the platform directory as a batch.

`check-operator-security.py` performs non-mutating operator inspection and audit
redaction checks. Set `PLATFORM_ADMIN_TOKEN` and `PLATFORM_TEST_PROJECT`; setting
`DEVELOPER_TOKEN` additionally enables developer-denial assertions. This diagnostic
explicitly reports that optional coverage as skipped when no developer token exists.

`verify-application-data-flow.py` runs inside a short-lived pod with disposable
`SOURCE_`, `ARTIFACT_`, and `SEARCH_` managed bindings and `FIXTURE_PARQUET_B64`.
Pass `--confirm-disposable-bindings`. It provisions a unique test schema and
synthetic artifacts/document, then removes its schema, exact object versions,
and document even on failure. It never deletes the bound database, bucket, or
index. The caller still owns provisioning and retirement of the project, pod,
and three bound resources; this command does not install a platform.
