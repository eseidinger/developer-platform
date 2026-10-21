# Platform API maintenance

Status: current implementation guide.

The Python/FastAPI application owns public APIs, platform metadata, grants,
deployment credentials, desired revisions, durable operations, policy,
Kubernetes execution, PostgreSQL provisioning, observation, diagnostics, and
audit. Its modules are internal responsibility boundaries, not independently
deployed services.

Named resources, grants, leases, provider adapters and recovery are under
`app/stores`; deployment uses explicit component bindings. `access_*` owns hosted
identity/policy reconciliation, and `ai_*` owns bounded assistance and approved
rollback proposals. These domains share the API authority boundary and durable
catalog but have distinct versions, credentials and recovery guards.

The source-adjacent [platform README](../../platform/README.md) documents local
configuration and validation. The durable design is described in
[Platform application](../architecture/platform-application.md) and
[Application lifecycle](../architecture/application-lifecycle.md).

Minimum local validation for API changes:

```bash
uv sync --project platform/app
uv run --project platform/app python -m unittest discover -s platform/app/tests -v
uv run --project platform/app python scripts/generate/export_openapi.py --check
python3 scripts/generate/generate-cli-contract.py --check
uv run --project platform/app python -m compileall -q platform/app/src/app scripts operations
```

Regenerate and check `docs/api/openapi.json` whenever the public schema changes.
Update the application declaration reference and compatibility notes in the same
change. New endpoints or persisted state also require scoped authorization,
revocation behavior, audit/redaction tests, and backup/recovery review.
