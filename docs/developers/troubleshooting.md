# Developer troubleshooting

Status: current. Last reviewed October 9, 2026.

These are failures visible to an application developer. Shared-service and host
incidents belong in the [operator runbooks](../operators/runbooks/README.md).

## Common failures

| Symptom | Meaning and next action |
| --- | --- |
| `PLATFORM_API_URL is required` | Set the API URL in the process environment. |
| Deployment credential is incomplete | Set all of `PLATFORM_TOKEN_ENDPOINT`, `PLATFORM_CLIENT_ID`, and `PLATFORM_CLIENT_SECRET`, or use only `PLATFORM_ACCESS_TOKEN`. |
| `401` or `403` | The credential is invalid, expired, revoked, or lacks deployment access to this project. Ask a project administrator to verify its scope. |
| `409` with `revision_conflict` | Refresh the current project revision and retry with the appropriate `--if-match` value. |
| `422` with `invalid_spec` or `unsupported_capability` | Correct the JSON or remove a capability the current environment does not support. |
| The operation fails or never becomes ready | Confirm that the image is public and pullable, the process listens on the declared port, and it meets the runtime restrictions above. Then inspect the operation in the UI or API. |

For a field-by-field guide, see the [application schema reference](application-spec.md).
The generated [OpenAPI contract](../api/openapi.json) remains the machine-readable
source of truth.
