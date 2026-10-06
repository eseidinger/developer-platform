# Platform CLI Implementation Plan

Status: planned as of October 6, 2026. The Platform API and the reference
`platform-cli` OIDC client exist, and Device Authorization with PKCE has been
exercised manually. No domain CLI package exists in source yet.

This plan delivers the CLI portion of PLAN-006 over the same versioned Python
Platform API used by the portal. It follows the identity boundary in
[ADR-004](../03-decisions/ADR-004-identity-and-access-management.md), the
technology-independent contract principle in
[ADR-001](../03-decisions/ADR-001-platform-api-abstraction.md), and the Phase 3
outcome in [Developer Experience and Access](phase-3-developer-experience.md).

## Outcome and scope

Deliver the `developer-platform-cli` Python distribution with an installed `devplat`
command that lets a human developer or operator:

1. authenticate without giving the CLI a password;
2. discover authorized projects and capabilities;
3. submit and follow deployments and lifecycle operations;
4. inspect readiness, resources, usage, revisions, drift, configuration metadata,
   secret metadata, and bounded logs;
5. manage configuration, secrets, rollback, restart, retirement, grants, and
   deployment credentials when the API authorizes the caller; and
6. use stable JSON output and exit codes from scripts without scraping terminal
   formatting.

The CLI is an API client only. It does not talk directly to Kubernetes, PostgreSQL,
Docker, or Keycloak administration APIs; duplicate authorization policy; accept the
legacy shared platform token; or expose credentials that the Platform API does not
return. Human database tunnels, hosted-application OIDC, and the application
template remain separate Phase 3 work packages.

## Proposed implementation stack

Use Python 3.12 or newer and package the CLI independently from FastAPI:

| Concern | Selection | Reason |
|---|---|---|
| Command framework | Typer / Click | Typed options, help, completion, prompts, and mature exit handling |
| HTTP | HTTPX | Timeouts, streaming, TLS configuration, and deterministic test transports |
| Boundary models | Pydantic | Strict validation of API responses that remain `unknown` in OpenAPI |
| Human output | Rich | Tables, progress, status, and stderr rendering with plain-output fallback |
| Configuration | platformdirs + TOML | Cross-platform, non-secret endpoint/profile configuration |
| Secret storage | keyring | OS credential storage; no plaintext token file |
| Tests | pytest + respx | Unit, transport, output, and error-contract coverage |
| Distribution | `developer-platform-cli` via `pyproject.toml`, wheel, and pipx | Distinct package identity, isolated install, and reproducible release artifacts |

The executable is named `devplat` to remain recognizable without colliding with
generic `platform` or `platformctl` commands. The Python import package remains
`platform_cli`. The existing OIDC public-client identifier remains `platform-cli`;
it is a protocol configuration value, not the executable or distribution name.

Device Authorization with PKCE is the required first human login flow because it
works locally, over SSH, and without a callback listener. Authorization Code with
PKCE may be added later for desktop convenience, but the CLI must never collect a
user password. Implement the device flow against standard OIDC endpoints; do not
couple command behavior to Keycloak administration APIs.

Record the stack in a dedicated ADR before the first release if implementation finds
a material alternative or adds a long-lived dependency not listed here.

## Runtime and security model

- Store only non-secret profile data in the configuration file: API URL, issuer,
  client ID, CA bundle path, output preference, and active profile name.
- Keep access tokens in process memory. If refresh/session persistence is enabled,
  store it only through the OS keyring, bound to profile, issuer, client ID, and
  subject. `devplat auth logout` removes it.
- Support both a pre-issued `PLATFORM_ACCESS_TOKEN` and deployment credentials from
  `PLATFORM_TOKEN_ENDPOINT`, `PLATFORM_CLIENT_ID`, and
  `PLATFORM_CLIENT_SECRET`. The CLI exchanges a complete deployment-credential set
  through the OIDC client-credentials flow, keeps the resulting access token only in
  process memory, and never persists the client secret. A partial set fails closed
  with the missing variable names. Environment authentication takes precedence over
  an interactive human session and is reported as non-persistent by `auth status`.
- Accept `PLATFORM_API_URL` and `PLATFORM_CA_BUNDLE` for non-interactive jobs so a
  deployment can run without first creating a local profile. Environment values are
  read once at process start and are never printed by status or debug output.
- Never accept bearer tokens, secret values, client secrets, or database passwords
  as command-line arguments because process listings and shell histories can expose
  them. Read secret input from a hidden prompt, stdin, or an explicitly selected
  file with restrictive-permission checks.
- Send progress, warnings, and errors to stderr. Reserve stdout for requested data
  so piping `--output json` is deterministic.
- Redact authorization headers and token/password/credential/private-key/secret
  fields from diagnostics. `--debug` may show safe method, URL, status, timing, and
  correlation ID, but never sensitive headers or bodies.
- Verify TLS by default. A profile may select a CA bundle. Any local-only insecure
  switch must be explicit per invocation and produce a warning.
- Treat server authorization as authoritative. Local role hints improve usability
  but never constitute an authorization boundary.

## Target source layout

```text
platform/cli/
  pyproject.toml
  README.md
  src/platform_cli/
    __init__.py
    __main__.py
    app.py                 # Typer root and global options
    config.py              # profiles and non-secret settings
    auth/
      device.py            # Device Authorization + PKCE
      session.py           # in-memory access and keyring-backed session state
    api/
      client.py            # one HTTPX client and bearer injection
      errors.py            # status/error-code mapping and correlation IDs
      models.py            # strict public response models
      contract.py          # OpenAPI compatibility/version checks
    commands/
      auth.py
      projects.py
      deploy.py
      operations.py
      diagnostics.py
      configuration.py
      secrets.py
      access.py
      credentials.py
      operator.py
    output/
      render.py            # table/json/yaml/plain boundary
      progress.py
    tests/
      fixtures/
      test_*.py
```

Feature commands call one API client and return domain values to the output layer.
They do not print from transport/model code. Generated or checked contract artifacts
must be reproducible and never edited manually.

## Command and output contract

Global options:

```text
devplat [--profile NAME] [--api-url URL] [--output table|json|yaml|plain]
        [--no-color] [--quiet] [--debug] COMMAND
```

Initial command surface:

```text
devplat auth login|status|logout
devplat capabilities get
devplat projects list|create|show
devplat deploy apply --project NAME --file SPEC [--wait]
devplat operations get|watch OPERATION_ID
devplat status PROJECT
devplat resources PROJECT
devplat usage PROJECT
devplat logs PROJECT [--component NAME] [--instance NAME] [--tail N]
                    [--since DURATION] [--search TEXT] [--follow]
devplat revisions list PROJECT
devplat rollback PROJECT --revision N [--wait]
devplat restart PROJECT [--wait]
devplat config get|replace PROJECT
devplat secrets list|set|delete|confirm|revert PROJECT [NAME]
devplat retirement preview|apply PROJECT
devplat grants list|set|delete PROJECT
devplat credentials list|create|rotate|revoke PROJECT
devplat operator ...
```

Authentication selection is deterministic: `PLATFORM_ACCESS_TOKEN` first, then a
complete deployment-credential environment, then the active human profile/session.
The CLI does not silently combine fields from different sources.

Names and flags follow the public domain vocabulary, not Kubernetes terms. Mutating
commands show a preview when the API supplies one and require confirmation when
interactive. Non-interactive destructive use requires an explicit name/scope
confirmation; `--yes` alone must not bypass name or scope-token checks.

`--output json` is the stable automation interface. Stdout is one JSON value,
contains API field names unless a versioned CLI envelope is documented, and never
contains progress text. Human tables may evolve without a compatibility promise.
One-time credential creation/rotation intentionally returns secret material: human
mode displays it once; JSON mode writes the response only to stdout with a warning on
stderr and is covered by no-log/no-artifact tests.

Use stable process exit codes:

| Code | Meaning |
|---:|---|
| 0 | Success, including a watched operation reaching its requested healthy state |
| 2 | CLI usage, local validation, or malformed input |
| 3 | Authentication required or invalid/expired human session |
| 4 | Authenticated but forbidden |
| 5 | Requested resource not found |
| 6 | Conflict, stale revision, blocker, or scope change |
| 7 | API validation/capability rejection |
| 8 | Rate limit, provider/API unavailable, or network failure |
| 9 | Durable operation completed unsuccessfully |
| 10 | Client-side watch timeout or interruption |

The JSON error form includes HTTP status, stable API `code` when present, safe
detail, correlation/request ID when supplied, and retryability. It never includes a
traceback unless an explicit development-only flag is active, and remains redacted.

## Delivery increments

### 0. Package, contract, and test foundation

- Create the isolated package, console entry point, reproducible lock/constraints
  policy, lint/type/test/build tasks, and pipx installation documentation.
- Add one HTTPX client with required timeouts, User-Agent/version, bearer injection,
  TLS/CA support, safe request IDs, response-size limits, and error normalization.
- Add strict response models for the endpoints used by each increment. Check that
  referenced paths/methods exist in `docs/api/openapi.json`; fail CI on drift.
- Establish golden tests for table/plain/JSON rendering and a transport fixture that
  proves stdout/stderr separation.

Gate: a clean checkout builds a wheel, installs it into an isolated environment,
runs `devplat --help`, and passes format, lint, type, unit, contract, and packaging
checks.

### 1. Deployment-credential authentication and apply

- Read `PLATFORM_API_URL`, `PLATFORM_TOKEN_ENDPOINT`, `PLATFORM_CLIENT_ID`, and
  `PLATFORM_CLIENT_SECRET` from the environment. Optionally honor
  `PLATFORM_CA_BUNDLE`. Validate that the required set is complete before making a
  request and never reproduce any value classified as secret in an error.
- Exchange the deployment credential using `grant_type=client_credentials`, apply
  the returned bearer token only in memory, and discard it when the process exits.
  Do not put the client ID, client secret, or access token in argv, a profile, the OS
  keyring, debug output, exception text, or command results.
- Implement `devplat deploy apply --project NAME --file SPEC [--wait]`, with `-` as
  stdin. Accept the versioned JSON application envelope first; add YAML only after
  the open format decision. Perform local parse/version checks, while keeping API
  validation and authorization authoritative.
- Parse the accepted operation response, print its operation ID and revision, and
  implement bounded `--wait` polling that distinguishes durable apply state from
  live readiness. On timeout or SIGINT, print the operation ID for later inspection;
  do not imply the durable operation was cancelled.
- Add deterministic fixtures for successful exchange/deployment, invalid client,
  expired/revoked credential, cross-project denial, malformed spec, API validation,
  queued/running/succeeded/failed operations, readiness failure, timeout, TLS error,
  and unavailable token/API endpoints.
- Provide a CI example with shell tracing disabled around environment setup and
  token exchange. The example must not echo, persist, or upload the client secret.

Gate: from a clean pipx install and no human profile, a CI-style process receives a
project deployment credential only through environment variables, submits a versioned
application spec, follows the operation to ready, and receives stable nonzero exits
for revoked, foreign-project, invalid-spec, failed-readiness, and timeout cases. No
credential or bearer token appears in argv, stdout/stderr diagnostics, logs, test
artifacts, or CLI storage.

### 2. Profiles and human authentication

- Implement profile create/show/use/delete for non-secret API and OIDC configuration.
  Seed a local profile from `/portal/config` where appropriate.
- Implement Device Authorization with a fresh PKCE verifier/challenge, bounded
  polling for `authorization_pending`, `slow_down`, denial, expiry, and interruption,
  plus browser-open and copyable verification URL/user code.
- Keep the access token in memory and place only permitted refresh/session material
  in the OS keyring. Implement status, renewal, logout, issuer/client/profile binding,
  and clear failure guidance when no keyring backend is available.
- Prove tokens and PKCE values are absent from argv, config files, stdout errors,
  debug output, crash traces, and test artifacts.

Gate: a human signs in through the reference Keycloak realm, lists projects, renews
or signs in again after access-token expiry, logs out, and cannot use the removed
session.

### 3. Read-only discovery and diagnosis

- Implement capabilities, project list/show, current status, operations get/watch,
  component state, resources, usage, revisions, drift, configuration metadata,
  secret metadata, data-service status, and deployment-credential metadata.
- Implement bounded logs with component/instance filters, time bounds, search,
  cursors, follow mode, cancellation, and explicit unavailable/truncated states.
- Keep desired revision, durable apply outcome, and live readiness separate in both
  human and JSON output. Never translate missing metrics to zero or provider failure
  to an empty result.
- Make operation/log watches resilient to transient network failures with bounded
  backoff, overall timeout, SIGINT handling, and no mutation retry.

Gate: viewer and developer identities see only authorized projects and can diagnose
an injected image-pull failure using status, operation, resource, revision, and log
commands without cluster access.

### 4. Broader deployment and lifecycle mutations

- Extend apply with `If-Match`, idempotent retry guidance, capability-aware feedback,
  and conflict output that retains the submitted file and reports the current
  revision. Add YAML only if selected after the first JSON deployment increment.
- Add configuration replacement from file/stdin, restart, rollback, secret lifecycle,
  and retirement preview/apply using the pinned scope token.
- Secret values use hidden prompt/stdin/file input only. Never echo them, insert them
  into exception text, cache them, or include them in shell-completion data.
- Require explicit confirmation for rollback, secret deletion/confirmation,
  credential revocation, and retirement. Preserve API blocker/retention details.

Gate: the complete developer journey creates a project, deploys a sample, follows
readiness, changes configuration/secrets, restarts, rolls back, and retires safely;
conflict, denial, validation, and provider-unavailable paths produce stable exits.

### 5. Access and automation administration

- Add project grant list/set/delete using immutable issuer/subject references and
  display names only as labels. Explain that revocation applies on the next request.
- Add deployment-credential list/create/rotate/revoke. Protect one-time client
  secrets from terminal history, diagnostics, captures, and test reports; never save
  them in CLI config or keyring as a side effect.
- Retain support for both deployment-credential environment exchange and an already
  issued `PLATFORM_ACCESS_TOKEN`, while keeping human and machine authentication
  sources distinct and visible in safe `auth status` output.
- Keep test-runner/test-persona administration under an explicitly named
  `devplat operator test-identities` tree if operational CLI use is required.

Gate: project-admin and platform-admin personas perform allowed administration;
viewer/developer and cross-project attempts fail server-side with stable exits; a
rotated/revoked credential follows the API lifecycle contract.

### 6. Operator commands and release hardening

- Add explicit `operator` commands for capacity, redacted audit export, permission
  inspection, security configuration, retirement inspection, recovery-request
  review, security-alert state, and selected public operator endpoints.
- Add completion generation, man/help snapshots, supported-platform packaging,
  dependency/license review, and signed/checksummed artifacts if releases leave the
  repository.
- Exercise proxy/direct-loopback endpoints, custom local CA trust, IPv4/IPv6 where
  supported, API incompatibility, rate limiting, terminal widths, non-TTY piping,
  Unicode, and interrupted watches.
- Publish upgrade and rollback instructions. Report CLI version and observed API
  compatibility before suggesting an upgrade.

Gate: developer and operator journeys pass on Linux and supported WSL, pipx
installation is reproducible, and a prior CLI release either performs its compatible
read-only commands or fails clearly.

## Operation watching and retry rules

- Poll only accepted operation/status URLs and stop on terminal durable state plus
  the command's readiness condition. Apply success is not workload readiness.
- Default waits are bounded and configurable. Show the operation ID on timeout so
  the user can resume with `operations watch`.
- Retry GETs only for selected transport failures, `429`, and transient `5xx`, using
  bounded backoff and `Retry-After`. Do not automatically retry a mutation unless its
  endpoint has a documented repeat/idempotency contract.
- SIGINT stops local waiting and returns code 10; it does not cancel a durable
  platform operation. State that distinction in the message.
- Redirected output disables animated progress automatically.

## Testing and acceptance matrix

| Layer | Required evidence |
|---|---|
| Static | Formatting, strict typing, lint, dependency policy, OpenAPI path freshness |
| Unit | PKCE, configuration, redaction, duration parsing, status mapping, exits, rendering |
| Transport | Timeouts, TLS, correlation IDs, retries, pagination/cursors, response bounds |
| Command | Help, prompts, stdin/file input, JSON stdout, stderr progress, SIGINT |
| Contract | Success and documented 400/401/403/404/409/422/429/5xx fixtures per endpoint |
| Authentication | Device pending/slow/denied/expired/success, renewal, logout, no-keyring behavior |
| Authorization | Viewer/developer/project-admin/platform-admin and cross-project denial matrix |
| Security | No bearer/refresh/client/application secret in argv, config, logs, tracebacks, captures, fixtures, or reports |
| End to end | Login, discover, deploy/watch, diagnose failure, configure, rollback/restart, retire, credential lifecycle |
| Packaging | Clean wheel, pipx install/upgrade/rollback, supported Python/OS matrix |

## Documentation and operational handoff

- Add a concise CLI README, installation/profile/authentication guide, command
  reference, JSON/exit-code contract, troubleshooting, and examples without real
  subjects, tokens, or secrets.
- Replace manual curl sequences in developer runbooks only after the CLI command has
  equivalent diagnostics and failure behavior. Keep curl for break-glass diagnosis.
- Record the exact CLI version in acceptance evidence and installation records and
  document minimum/compatible API versions.
- Provide CI examples that mask one-time secrets and disable shell tracing around
  credential exchange; do not encourage personal-token reuse.

## Completion criteria

The CLI is complete when the Phase 3 create/deploy/observe/diagnose/recover/retire
journey is reproducible against the deployed Platform API; human and automation
authentication remain separate; machine-readable output and exit codes are tested;
the role/denial matrix passes through direct CLI commands; secrets are absent from
storage and artifacts outside explicit one-time/input paths; and install, upgrade,
rollback, and compatibility evidence is recorded in the delivery backlog.

## Open decisions before increment 1

- Whether the public CLI client issues a refresh token that may be stored in the OS
  keyring, or each new process performs Device Authorization. Access tokens remain
  memory-only either way.
- Whether YAML is included initially or JSON is the only stable machine format.
- The compatibility mechanism: a dedicated API version endpoint is preferable;
  otherwise use a documented OpenAPI/capability fingerprint.
- Supported hosts beyond Linux/WSL, especially keyring and CA behavior on macOS and
  Windows.
- Whether operator/test-identity commands are required for Phase 3 acceptance or
  remain API/runbook-only after the developer CLI gate.
