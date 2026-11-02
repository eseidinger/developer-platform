# Developer troubleshooting

Status: current. Last reviewed October 18, 2026.

These are failures visible to an application developer. Shared-service and host
incidents belong in the [operator runbooks](../operators/runbooks/README.md).

## Common failures

- **Symptom:** `PLATFORM_API_URL is required`
  - **Meaning and next action:** Set the API URL in the process environment, a
    selected CLI profile, or `--api-url`.
- **Symptom:** Deployment credential is incomplete
  - **Meaning and next action:** Set all of `PLATFORM_TOKEN_ENDPOINT`,
    `PLATFORM_CLIENT_ID`, and `PLATFORM_CLIENT_SECRET`, or use only
    `PLATFORM_ACCESS_TOKEN`.
- **Symptom:** `401` or `403`
  - **Meaning and next action:** The credential is invalid, expired, revoked, or
    lacks deployment access to this project. Ask a project administrator to
    verify its scope.
- **Symptom:** `409` with `revision_conflict`
  - **Meaning and next action:** Refresh the current project revision and retry
    with the appropriate `--if-match` value.
- **Symptom:** Store binding is unavailable
  - **Meaning and next action:** Inspect the named resource and binding's
    desired/observed state. The exact component binding must be approved and
    active; unbound applications receive no automatic database.
- **Symptom:** Legacy database issuance returns `410`
  - **Meaning and next action:** Use named resources, explicit human grants and
    expiring leases through `devplat stores` or **My store access**.
- **Symptom:** AI assistance is ineligible
  - **Meaning and next action:** A human platform administrator sets the
    separate AI classification to Public/Internal; provider credentials and
    processing eligibility must also be configured.
- **Symptom:** `422` with `invalid_spec` or `unsupported_capability`
  - **Meaning and next action:** Correct the JSON or remove a capability the
    current environment does not support. In particular, remove `OTEL_*` names
    from `spec.configuration.values`; the platform injects its tracing settings
    for opted-in components.
- **Symptom:** The operation fails or never becomes ready
  - **Meaning and next action:** Confirm that the image is public and pullable,
    the process listens on the declared port, and it meets the runtime
    restrictions above. Then inspect the operation in the UI or API.

For a field-by-field guide, see the
[application schema reference](application-spec.md). The generated
[OpenAPI contract](../api/openapi.json) remains the machine-readable source of
truth.
