# Platform API maintenance

Status: current implementation guide.

The Python/FastAPI application owns public APIs, platform metadata, grants,
deployment credentials, desired revisions, durable operations, policy,
Kubernetes execution, PostgreSQL provisioning, observation, diagnostics, and
audit. Its modules are internal responsibility boundaries, not independently
deployed services.

The source-adjacent [platform README](../../platform/README.md) documents local
configuration and validation. The durable design is described in
[Platform application](../architecture/platform-application.md) and
[Application lifecycle](../architecture/application-lifecycle.md).

Minimum local validation for API changes:

```bash
python3 -m pip install -r platform/requirements-dev.txt
python3 -m unittest discover -s platform/tests -v
python3 -m compileall -q platform scripts operations
```

Regenerate and check `docs/api/openapi.json` whenever the public schema changes.
Update the application declaration reference and compatibility notes in the same
change. New endpoints or persisted state also require scoped authorization,
revocation behavior, audit/redaction tests, and backup/recovery review.
