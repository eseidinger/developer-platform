# Platform CLI implementation plan

Status: source implemented; deployed acceptance remains open.
The Python package under `platform/cli` now has profiles, human device login,
environment authentication, deployment and operation commands, hosted access,
and explicit commands for 119 public API operations, plus a named-store PostgreSQL
SSH tunnel. The registry excludes two health probes, two legacy operations that
always return HTTP 410, and browser-only console launch. Local tests,
contract parity, and wheel packaging pass. Human login and an authorized project
list were observed from WSL on October 18, 2026; project/role denial, deployment,
and tunnel acceptance remain to be recorded.

This plan delivers the CLI portion of PLAN-006 over the same versioned Python
Platform API used by the portal. It follows the identity boundary in
[ADR-004](../../../architecture/decisions/ADR-004-identity-and-access-management.md), the
technology-independent contract principle in
[ADR-001](../../../architecture/decisions/ADR-001-platform-api-abstraction.md), and the Phase 3
outcome in [Developer Experience and Access](../history/phase-3-developer-experience.md).

## Outcome and scope

Deliver the `developer-platform-cli` Python distribution with an installed `devplat`
command that lets a human developer or operator:

1. authenticate without giving the CLI a password;
2. discover authorized projects and capabilities;
3. submit and follow deployments and lifecycle operations;
4. inspect readiness, resources, usage, revisions, drift, configuration metadata,
   secret metadata, and bounded logs;
5. perform every project administration action exposed by the public Platform
   API, including configuration, secrets, recovery requests, retirement, project
   grants, deployment credentials, governance, and hosted application access; and
6. use stable JSON output and exit codes from scripts without scraping terminal
   formatting.

The CLI is an API client only. It does not talk directly to Kubernetes, PostgreSQL,
Docker, or Keycloak administration APIs; duplicate authorization policy; accept the
legacy shared platform token; or expose credentials that the Platform API does not
return. Hosted application access administration consumes the existing generic
access API; it does not implement a new identity provider or application token
client. The CLI opens PostgreSQL tunnels for active named-store credentials;
bastion deployment and the application template remain separate work packages.

Full project administration means coverage of every current public
project-scoped API operation and its shared operation endpoints, subject to the
caller's server-side permissions. Operations requiring platform authority have
explicit `operator` commands. Unsupported actions, such as identity-provider
account creation, ownership transfer without an API contract, and
component-specific secret isolation, are recorded as API/product gaps;
the CLI must not bypass the API to approximate them.

## Project administration coverage

Implement a checked command-to-API registry with one entry per HTTP method and
path in [OpenAPI](../../../api/openapi.json). An entry records the command,
delivery increment, request/response model, concurrency and idempotency rules,
operation family, sensitive-output behavior, and authorization test cases.
CI rejects missing project/shared-operation entries and references to removed
endpoints. Explicit exclusions cover health probes and platform/operator-only
operations; internal control-plane endpoints are never CLI commands. A generic
HTTP escape hatch does not count as domain-command coverage.

The following families cover the current public project API. Paths are relative
to the API base URL; `{project}` and `{name}` both identify the selected project.
Each method and action listed must have its own registry entry.

| Administration task | Proposed command family | Current API coverage |
|---|---|---|
| Discover capabilities and projects; create an empty project | `capabilities get`, `projects list/create/show` | `GET /v1/capabilities`; `GET/POST /projects`; `show` selects the authorized entry from the project list, since there is no project-detail GET |
| Deploy and change component images, replicas, resources, schedules, ports, exposure, or egress | `deploy apply` | `PUT /projects/{name}` with a complete application declaration |
| Inspect and follow deployment operations | `operations get/watch` | `GET /v1/operations/{operation_id}` |
| Inspect components, resources, usage, drift, and revisions | `status`, `components list`, `resources`, `usage`, `drift`, `revisions list` | `GET /projects/{name}/components`, `/resources`, `/resource-usage`, `/drift`, `/revisions` |
| Restart and roll back | `restart`, `rollback` | `POST /projects/{name}/restart`, `/rollback` |
| Inspect current and retained logs | `logs`, `logs retained` | `GET /projects/{name}/logs`, `/retained-logs` with supported component, instance, time, search, and cursor filters |
| Inspect and replace configuration | `config get/replace` | `GET/PUT /projects/{name}/configuration` |
| Manage secret values and rotation | `secrets list/set/delete/confirm/revert` | `GET /projects/{name}/secrets`; `PUT/DELETE /projects/{name}/secrets/{secret}`; `POST` its `/confirm`, `/revert` |
| Inspect data services and request recovery | `data-services list`, `data-services recovery request` | `GET /projects/{name}/data-services`; `POST /projects/{name}/data-services/recovery-requests` |
| Preview and execute retirement | `retirement preview/apply` | `GET /projects/{name}/retirement-preview`; `POST /projects/{name}/retire` |
| Manage platform roles within a project | `grants list/set/delete` | `GET/PUT/DELETE /projects/{name}/grants` |
| Manage CI deployment credentials | `credentials list/create/rotate/revoke` | `GET/POST /projects/{name}/deployment-credentials`; `DELETE /{credential_id}` and `POST /{credential_id}/rotate` beneath that collection |
| Inspect hosted access eligibility and scoped operations | `access context`, `access operations list` | `GET /v1/projects/{project}/application-access-context`, `/application-access-operations` |
| Create, list, and delete application groups | `access groups list/create/delete` | `GET/POST /v1/projects/{project}/application-groups`; `DELETE /{resource_id}` beneath that collection |
| Inspect, apply, and roll back route policies | `access policy get/apply/revisions/rollback` | `GET/PUT /v1/projects/{project}/applications/{application}/access-policy`; `GET /revisions` and `POST /rollback` beneath that policy |
| Review and transition human access requests | `access human-requests list/approve/reject/reopen/cancel/assign-groups` | `GET /v1/projects/{project}/application-access-requests`; `POST /{resource_id}/approve`, `/reject`, `/reopen`, `/cancel`, `/groups` beneath that collection |
| Inspect and revoke application group memberships | `access memberships list/revoke` | `GET /v1/projects/{project}/application-group-memberships`; `DELETE /{resource_id}` beneath that collection |
| Manage outgoing and incoming machine access | `access services list/request/approve/reject/cancel/rotate/confirm/revoke` | `GET/POST /v1/projects/{project}/service-access-requests`; `DELETE /{resource_id}` and `POST /{resource_id}/approve`, `/reject`, `/cancel`, `/rotate`, `/confirm` beneath that collection |
| Follow and retry hosted access reconciliation | `access operations get/watch/retry` | `GET /v1/access-operations/{operation_id}`; `POST /{operation_id}/retry` beneath `/v1/access-operations` |
| Inspect and replace classification and retention metadata | `governance get/replace` | `GET/PUT /v1/projects/{project}/governance` |

Keep project grants, application groups, and CI credentials as separate command
families. A project administrator does not gain application route access by
managing it. Shared service credentials identify a project client, not the
individual worker using them. Project creation and individual administration
actions remain subject to the API role model; command availability does not
grant authority.

The operator increment separately covers every current public `/operator` and
`/platform` endpoint: capacity, audit export, project permission/security
inspection, retirement inspection and purge, recovery-request review, hosted
access recovery, platform grants, test-runner credentials, and test personas.
Do not invent commands for operator capabilities lacking a public endpoint.

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
PKCE is included in device login, and the CLI must never collect a
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
      governance.py
      data_services.py
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
devplat [--profile NAME] [--api-url URL] [--output table|json|plain]
        [--no-color] [--quiet] [--debug] COMMAND
```

Implemented command surface. `auth status` and `deploy apply` preserve their
existing invocation syntax while using common options. Administration commands
accept an explicit `--project NAME`; policies
also accept `--application NAME`. Selected-profile defaults may supply the
project, but mutations always show the resolved scope.

```text
devplat auth login|status|logout
devplat profiles create|show|use|delete
devplat capabilities get
devplat projects list
devplat projects create|show --project NAME
devplat deploy apply --project NAME --file SPEC [--wait]
devplat operations get|watch OPERATION_ID
devplat status --project NAME
devplat components list --project NAME
devplat drift --project NAME
devplat resources --project NAME
devplat usage --project NAME
devplat logs --project NAME [--component NAME] [--instance NAME] [--tail N]
                    [--since DURATION] [--search TEXT] [--follow]
devplat logs retained --project NAME [FILTERS]
devplat revisions list --project NAME
devplat rollback --project NAME --revision N [--wait]
devplat restart --project NAME [--wait]
devplat config get|replace --project NAME [--file DOCUMENT]
devplat secrets list|set|delete|confirm|revert --project NAME [SECRET_NAME]
devplat retirement preview|apply --project NAME
devplat grants list|set|delete --project NAME
devplat credentials list|create|rotate|revoke --project NAME [CREDENTIAL_ID]
devplat data-services list --project NAME
devplat data-services recovery request --project NAME --file REQUEST
devplat governance get|replace --project NAME [--file DOCUMENT]
devplat access context --project NAME
devplat access groups list|create|delete --project NAME
devplat access policy get|apply|revisions|rollback --project NAME
                      --application NAME [--file POLICY]
devplat access human-requests list|approve|reject|reopen|cancel|assign-groups
                              --project NAME [REQUEST_ID] [--group GROUP_ID]...
devplat access memberships list|revoke --project NAME [MEMBERSHIP_ID]
devplat access services list|request|approve|reject|cancel|rotate|confirm|revoke
                       --project NAME [REQUEST_ID]
devplat access operations list --project NAME
devplat access operations get|watch|retry OPERATION_ID
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

Hosted service-access commands never return a client secret or access token.
They display only access state, provider URL, audience, managed secret variable
names, and operation metadata. Managed access credentials must be rotated through
`access services`, preserving their provider lifecycle, rather than overwritten
with a generic `secrets set` command.

Use `--file PATH` or `--file -` for complete policy, configuration, governance,
and recovery-request documents. Resource identifiers and group IDs are ordinary
arguments. Group names may be accepted where the API resolves them; retain stable
IDs in machine output and approval previews. Policy rollback targets the API's
previous revision; it must not advertise arbitrary revision selection.

Versioned access mutations accept `--if-match ETAG` and preserve the API's quoted
ETag exactly. Read/list output includes the version and ETag needed for the next
mutation, deriving a quoted version only where the API contract specifies it.
Interactive commands may read the resource, preview the action, and submit with
that observed version. Non-interactive updates require an explicit version.
Initial creates omit `If-Match` only where the endpoint permits it. Stale versions
return conflict exit 6; never reread and silently overwrite after `412`. Missing
preconditions (`428` or documented `422`) use API validation exit 7. Extend the
existing HTTP error mapping and structured error output for these access responses.

Idempotent creates accept `--idempotency-key KEY`. Generate and report a key when
omitted so a caller can resume an uncertain create with the same key and payload;
scripts should supply a stable key. Reuse with changed content reports the API's
conflict. Retry an access operation with the target resource's current ETag and
renewed authority, not the operation's own version.

Asynchronous mutations accept `--wait`, `--timeout`, and `--poll-interval`.
Deployment and hosted-access operations have different schemas and terminal
conditions, handled by separate adapters over shared polling code. An access
grant succeeds when its operation finishes and the resource becomes active;
revocation succeeds when cleanup finishes. Approval, provisioning, revocation
pending, and completed cleanup remain distinct in output. Revocation messaging
explains the maximum five-minute authorization propagation bound.

`access services list` reports both outgoing and incoming requests using the
API-returned consumer and provider projects. Optional `--direction incoming|outgoing`
filters are local views; a same-project request belongs to both views and remains
one resource. Approval/rejection uses provider scope, creation/cancellation/
rotation/confirmation uses consumer scope, and revocation follows either owner's
authorized scope. The server decides permission, including when scopes coincide.

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

## Same project worker access example

The following is a planned CLI acceptance journey for an `orders` application
with public component `api` and private component `worker`. The administrator
creates a `workers` group, applies an access policy whose `/machine-api/` routes
use `bearer-token` and that group, then requests access from `orders` to `orders`.
Existing browser rules stay in the complete policy file.

```bash
devplat access groups create --project orders --name workers \
  --display-name Workers --idempotency-key orders-workers --output json
devplat access policy apply --project orders --application orders \
  --file access-policy.json --wait
devplat access services request --project orders --name worker-api \
  --provider-project orders --application orders --project-wide-credential \
  --idempotency-key orders-worker-api --output json
devplat access services list --project orders --output json
devplat access services approve --project orders "$REQUEST_ID" \
  --group "$GROUP_ID" --if-match "$REQUEST_ETAG" --wait --output json
```

Use the group ID, request ID, and quoted request ETag from the preceding results
for `GROUP_ID`, `REQUEST_ID`, and `REQUEST_ETAG`. Policy creation can omit
`--if-match`; an update supplies the current policy ETag. The active service
response identifies the provider URL and the secret prefix. The worker reads the
injected `<secretPrefix>_CLIENT_ID`, `_CLIENT_SECRET`, and `_TOKEN_URL`, obtains a
five-minute token, and sends it to the provider's public HTTPS route. Declare the
worker's HTTPS egress to both issuer and provider in its application specification
and apply it with `deploy apply`.

Acceptance verifies that the worker's direct call to the public backend is denied,
and that its authorized public call reaches the API with service principal
headers. Private-to-private component calls retain their existing in-project
connectivity. Credentials remain project-wide; this journey creates no
worker-specific security boundary. Repeat the request/approval journey with
different consumer/provider projects to exercise the ownership distinction.

## Delivery increments

Extend the existing package rather than starting another CLI. Foundation and
deployment support have partial source implementation; audit them against their
remaining gates. Build shared administration infrastructure and human login next,
then deliver access discovery and increment 4a as the first administration slice.
Complete the broader diagnosis, lifecycle, grants, and credential commands after
that slice. Access commands depend on the public hosted-access API, not completion
of every deployment/lifecycle command. Operational acceptance retains the
existing Phase 3 dependencies; a written plan does not close a delivery gate.

### 0. Package, contract, and test foundation

- Create the isolated package, console entry point, reproducible lock/constraints
  policy, lint/type/test/build tasks, and pipx installation documentation.
- Add one HTTPX client with required timeouts, User-Agent/version, bearer injection,
  TLS/CA support, safe request IDs, response-size limits, and error normalization.
- Add strict response models for the endpoints used by each increment. Check that
  referenced paths/methods exist in `docs/api/openapi.json`; fail CI on drift.
- Add the administration coverage registry and report planned versus implemented
  commands. A new public project or shared-operation endpoint requires a mapping
  and delivery task; enforce complete implementation before the parity gate closes.
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
  Seed API and issuer settings from `/portal/config` where appropriate, using the
  CLI's `platform-cli` client ID rather than copying the portal's browser client ID.
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
  secret metadata, data-service status, and deployment-credential metadata. Include
  retained logs with the endpoint's supported filters and retention limits.
- Deliver access context, group/policy/request/membership/service listings,
  governance, policy revisions, and access operation list/get/watch early, using
  the same response models and operation adapters as increment 4a.
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

- Implement empty-project creation with the API's documented request and role
  requirements, preserving the separate first-deployment workflow.
- Extend apply with `If-Match`, idempotent retry guidance, capability-aware feedback,
  and conflict output that retains the submitted file and reports the current
  revision. Add YAML only if selected after the first JSON deployment increment.
- Add configuration replacement from file/stdin, restart, rollback, secret lifecycle,
  data-service recovery requests, and retirement preview/apply using the pinned
  scope token. Change images, scaling, schedules, exposure, resources, and egress
  through the complete application declaration; do not invent patch endpoints.
- Secret values use hidden prompt/stdin/file input only. Never echo them, insert them
  into exception text, cache them, or include them in shell-completion data.
- Require explicit confirmation for rollback, secret deletion/confirmation,
  credential revocation, and retirement. Preserve API blocker/retention details.

Gate: the complete developer journey creates a project, deploys a sample, follows
readiness, changes configuration/secrets, restarts, rolls back, and retires safely;
conflict, denial, validation, and provider-unavailable paths produce stable exits.

### 4a. Hosted application access administration

- Implement application-group create/delete with idempotent creation and referenced
  group blockers; governance get/replace with classification and retention fields.
- Implement complete access-policy apply, inspection, revision history, and previous
  revision rollback. Show component, path/method, authentication mode, and allowed
  groups before applying. Preserve explicit deny behavior and server validation
  for overlaps, reserved paths, missing groups, and governance/email dependencies.
- Implement human-request approve/reject/reopen/cancel/assign-groups and membership
  revocation. Human requests originate at first browser login; do not add a command
  to create realm accounts or fabricate first-login requests.
- Implement service request/approve/reject/cancel/rotate/confirm/revoke. Require
  acknowledgment of project-wide credential sharing on request creation, represented
  by `--project-wide-credential` in scripts. Require explicit groups on approval;
  never select an administrator group by default.
- Support a consumer requesting its own application's public service with identical
  consumer/provider project names. Do not require another project or pretend the
  request name binds the credential to a specific worker component.
- Show managed variable names, public provider URL, and HTTPS egress prerequisites
  after activation. The worker implements its application-token exchange; the CLI
  manages the access resource without obtaining or displaying its service secret.
- Implement normal and emergency service rotation plus explicit adoption
  confirmation. Explain the at-most-24-hour normal overlap and absence of emergency
  overlap; never confirm adoption automatically when provisioning succeeds.
- Implement access-operation retry with resource preconditions and authorized
  project-scoped operation visibility. Preserve failed/retrying/provider-cleanup
  states rather than reporting an approval submission as successful access.

Gate: project administrators complete policy/group/governance setup, first-login
approval and membership revocation, cross-project service access, and same-project
worker-to-public-service access using CLI commands. Prove pending denial, successful
approved calls, stale ETag conflicts, idempotent replay, wrong-group and wrong-owner
denial, normal/emergency rotation, explicit adoption, policy rollback, failed-provider
retry, and bounded revocation propagation. Service credentials remain only in the
managed project secret; project grants remain distinct from application membership.

### 5. Project grants and automation credentials

- Add project grant list/set/delete using immutable issuer/subject references and
  display names only as labels. Explain that revocation applies on the next request.
- Add deployment-credential list/create/rotate/revoke. Protect one-time client
  secrets from terminal history, diagnostics, captures, and test reports; never save
  them in CLI config or keyring as a side effect.
- Retain support for both deployment-credential environment exchange and an already
  issued `PLATFORM_ACCESS_TOKEN`, while keeping human and machine authentication
  sources distinct and visible in safe `auth status` output.
- Keep test-runner/test-persona administration under an explicitly named
  `devplat operator test-identities` tree in increment 6.

Gate: project-admin and platform-admin personas perform allowed administration;
viewer/developer and cross-project attempts fail server-side with stable exits; a
rotated/revoked credential follows the API lifecycle contract.

### 6. Operator commands and release hardening

- Add explicit `operator` commands for capacity, redacted audit export, permission
  inspection, security configuration, retirement inspection, purge preview/apply,
  recovery-request review, hosted-access recovery, platform grants, test-runner
  credentials, and test personas. Scope this increment to public API endpoints;
  record further operator capabilities as API gaps.
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
  the user can resume with `operations watch` or `access operations watch` for the
  corresponding operation family. Reject absolute/off-origin status URLs and
  redirects that could forward the Platform API bearer token elsewhere.
- Renew the selected identity during long watches when its authentication source
  permits it: re-exchange environment client credentials or refresh the human
  session. A supplied access token cannot be renewed by the CLI; report expiry
  and preserve the operation ID. Never switch identities or replay a mutation
  after authentication expires.
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
| Contract | Success and documented 400/401/403/404/409/412/422/428/429/5xx fixtures per endpoint |
| Administration coverage | Every public project/shared-operation method and path mapped to an implemented command; explicit platform/operator exclusions and API gaps |
| Authentication | Device pending/slow/denied/expired/success, renewal, logout, no-keyring behavior |
| Authorization | Viewer/developer/project-admin/platform-admin and cross-project denial matrix |
| Hosted access | Human request transitions, memberships, policies/revisions, governance, incoming/outgoing and same-project service access, failed-provider retry, rotation/adoption/revocation |
| Concurrency | Exact ETag forwarding, missing/stale preconditions, idempotency replay and changed-body conflicts, no silent overwrite or unsafe mutation retry |
| Security | No bearer/refresh/client/application secret in argv, config, logs, tracebacks, captures, fixtures, or reports |
| End to end | Login, discover, deploy/watch, diagnose failure, configure, request recovery, rollback/restart, retire, project grants, credential lifecycle, complete hosted-access administration |
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
- Publish the worker access example and full administrator command reference when
  implemented. Include separate recipes for human approvals, incoming/outgoing
  machine requests, policy rollback, credential adoption, and cleanup retry.

## Completion criteria

The CLI's full acceptance remains in Phase 10 until the create/deploy/observe/diagnose/recover/retire
journey is reproducible against the deployed Platform API; human and automation
authentication remain separate; machine-readable output and exit codes are tested;
the role/denial matrix passes through direct CLI commands; secrets are absent from
storage and artifacts outside explicit one-time/input paths; and install, upgrade,
rollback, and compatibility evidence is recorded in the delivery backlog.

Project administration parity additionally requires every current public project
and shared-operation endpoint to have a tested domain command. Complete both
human and machine hosted-access journeys, including same-project worker access,
governance, optimistic concurrency, failed-operation recovery, and credential
adoption. Track platform/operator coverage separately; excluded endpoints and
unavailable API capabilities must be explicit rather than silently counted as
supported. Future project API additions reopen the registry's coverage check.

## Remaining implementation decisions

- Whether the public CLI client issues a refresh token that may be stored in the OS
  keyring, or each new process performs Device Authorization. Access tokens remain
  memory-only either way.
- JSON remains the initial input and automation output format. Decide separately
  whether a later release adds YAML without changing the JSON contract.
- The compatibility mechanism: a dedicated API version endpoint is preferable;
  otherwise use a documented OpenAPI/capability fingerprint.
- Supported hosts beyond Linux/WSL, especially keyring and CA behavior on macOS and
  Windows.
- Project administration parity is the first CLI completion gate; the separately
  privileged operator command surface follows in increment 6. Agree its release
  boundary without postponing project administration coverage.
