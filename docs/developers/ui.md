# UI guide

Status: partially implemented. Last reviewed October 9, 2026.

The Platform Control Plane portal is served from the Platform API root. It uses
OIDC Authorization Code with PKCE and calls the same API as the CLI. The current
foundation provides the routed shell and authentication boundary; project
lifecycle screens remain under active delivery.

The UI may explain or hide actions based on the current role, but the Platform API
is authoritative for authorization, validation, audit, and redaction. Access
tokens and one-time secrets must not enter URLs, logs, screenshots, or persistent
browser storage.

Until a workflow is available in the portal, use the [CLI](cli.md) or
[API](api.md). For UI source, commands, and tests, see the
[UI maintainer guide](../maintainers/ui.md).
