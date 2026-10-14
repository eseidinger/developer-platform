# CLI guide

Status: source implementation, October 13, 2026. Deployed login and complete
administration acceptance have not yet been recorded.

`devplat` is a client for the public Developer Platform API. Install the Python
package and inspect the commands:

```bash
python3 -m pip install -e 'platform/cli[dev]'
devplat --help
devplat contract check --output json
```

The existing CI deployment invocation remains supported:

```bash
export PLATFORM_API_URL=https://platform.example
export PLATFORM_TOKEN_ENDPOINT=https://identity.example/realms/platform/protocol/openid-connect/token
export PLATFORM_CLIENT_ID='...'
export PLATFORM_CLIENT_SECRET='...'
devplat deploy apply --project orders --file application.json --wait
```

An externally obtained `PLATFORM_ACCESS_TOKEN` takes precedence over the client
credential variables. A project deployment credential can deploy and inspect one
project; it cannot configure application access, grant roles, or manage credentials.
The client ID and secret never belong in CLI arguments or a profile.

## Profiles and human login

A profile contains non-secret API and OIDC settings. The `platform-cli` public
client ID is the default. A profile is not an authorization grant.

```bash
devplat profiles create lab --api-url https://platform.example \
  --issuer https://identity.example/realms/platform --project orders
devplat profiles use lab
devplat auth login
devplat auth status --output json
```

Login uses OIDC Device Authorization with PKCE. Follow the printed verification
URL and user code. The CLI keeps access tokens in memory and binds any renewable
session to its profile, issuer, client ID, and subject in the OS keyring. If no
secure keyring is available, use an externally supplied short-lived administrator
access token. `devplat auth logout` clears the local session and requests provider
revocation. `devplat profiles delete lab` clears its bound session as well.

For human profile authentication, clear `PLATFORM_ACCESS_TOKEN`,
`PLATFORM_TOKEN_ENDPOINT`, `PLATFORM_CLIENT_ID`, and `PLATFORM_CLIENT_SECRET` from
the shell. Environment authentication takes precedence over a profile session.
Use `--profile NAME` to select another profile for one command. `PLATFORM_API_URL`
and `PLATFORM_CA_BUNDLE` may override the profile for a process.

## Project administration

Commands are grouped by task. `devplat projects`, `components`, `status`,
`operations`, `resources`, `usage`, `drift`, `revisions`, and `logs` inspect
authorized project state. `deploy apply` sends a complete declaration; `config`,
`secrets`, `restart`, `rollback`, `data-services`, and `retirement` manage its
lifecycle. `grants` and `credentials` manage project roles and CI identities.
`governance` and `access` manage hosted application identity. Commands under
`operator` require their corresponding privileged API role.
`database-access` manages distinct, audited human PostgreSQL grants, SSH keys,
and one-time passwords; see the [human database access guide](database-access.md).
`operator audit export --start TIMESTAMP --end TIMESTAMP --format csv` writes the
bounded CSV response to stdout; the default JSON format uses normal output modes.

Use `--output json` for machine output on stdout. Progress, recovery IDs, and
warnings go to stderr. `logs --follow` emits successive JSON objects while it
runs. `--debug` shows only method, API path, status, timing, and request ID.
Authentication, authorization, conflict, invalid input, unavailable service,
failed durable operation, and interrupted watching use distinct exit codes;
the [implementation plan](../maintainers/delivery/plans/cli.md#command-and-output-contract)
defines them.

Updates to hosted access resources use the quoted ETag returned by an earlier
read or create response:

```bash
devplat access groups list --project orders --output json
devplat access policy get --project orders --application orders --output json
devplat access policy apply --project orders --application orders \
  --file access-policy.json --if-match '"3"' --wait
```

`access policy apply`, `config replace`, and `governance replace` read a complete
JSON document from `--file PATH` or `--file -`. Access policy updates replace the
entire policy, including existing browser rules. Required ETags are never
silently retried after a version conflict. Idempotent group and service creates
accept `--idempotency-key`; if omitted, the CLI prints a generated key on stderr
so an uncertain request can be retried with the same key and body.

## Worker access to its application's public service

After declaring a `bearer-token` route on the public component, a project
administrator can request and approve service access within the same project:

```bash
devplat access groups create --project orders --name workers \
  --display-name Workers --idempotency-key orders-workers --output json
devplat access policy apply --project orders --application orders \
  --file access-policy.json --wait
devplat access services request --project orders --name worker-api \
  --provider-project orders --application orders --project-wide-credential \
  --idempotency-key orders-worker-api --output json
devplat access services approve svc_REQUEST_ID --project orders \
  --group grp_GROUP_ID --if-match '"1"' --wait --output json
```

Use the actual request ID, group ID, and current quoted request ETag from the
preceding results. The provider project administrator approves incoming access;
the consumer chooses no groups. The active response reports the provider URL,
audience, and managed secret prefix. The service client ID, secret, and token URL
are injected into the consumer project's managed secret, visible to its
components. The worker obtains short-lived application tokens and calls the
public HTTPS route. Declare outbound HTTPS to both the issuer and provider in
the worker's application declaration. The CLI does not read or display the
managed service client secret.

Use `access services rotate` to provision a replacement credential, then
`access services confirm` after the workload adopts it. `--emergency` on rotate
removes old-client authority without overlap. Use `access operations watch` to
follow reconciliation and `access operations retry OPERATION_ID --if-match '"N"'`
to retry a failed resource operation with its current ETag. A submitted approval
is not usable access until provisioning completes.

Secret input is accepted from a hidden prompt, stdin, or an owner-only regular
file via `--value-file`; it is never an argument value. CI credential creation
and rotation intentionally return a one-time secret. Capture it in a protected
secret store without shell tracing. Destructive commands require
`--confirm-project NAME` matching the target scope, or `platform` for a
platform-wide operator action.
