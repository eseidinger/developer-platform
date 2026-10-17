# Named data-store resources

Phase 7 implementation is in progress. PostgreSQL named resources, the API/CLI,
portal and private lease relay are implemented in source and disposable tests.
The pinned AGE/pgvector image and pgAdmin SSO configuration are in source.
Disposable console SSO/connection acceptance passes; provider expansion,
backup/restore and deployed acceptance are still being completed. No existing installation has been reset.

## Resource and binding workflow

A project administrator creates resources owned by their project. Platform
administrators have these capabilities across projects; direct data access still
requires an explicit human grant. Shared-service installation and capacity remain
operator responsibilities. Creating a resource does not deploy an application.

Create an empty project if needed, then use `devplat stores create --project NAME
--file resource.json`, where the file contains, for example:

```json
{"name":"primary","provider":"postgresql","quota_bytes":1073741824,"extensions":[]}
```

`devplat stores get RESOURCE_UUID` reports desired/observed state and any fixed
provider error code. Wait for `observed_state=active`. Names can change; resource
UUIDs and provider identities do not. PostgreSQL extensions are selected per
resource database and require the matching operator-installed extension build.

Request component access using `devplat stores bindings request --project NAME
--file binding.json`:

```json
{"resource_id":"RESOURCE_UUID","component":"web","mode":"read-write"}
```

Use a real resource UUID. A same-project administrator's request is approved;
a cross-project request remains pending until a resource-owning administrator
(or platform administrator) explicitly approves that exact grant/version/mode.
`stores grants approve GRANT_UUID --file approval.json` accepts an `approve`
boolean and the current `version`. Permission increases for foreign-project
bindings require a new request. No pending request supplies credentials.

Wait for binding `observed_state=active`, then put the returned binding UUID
inside the target v1alpha2 component:

```json
"bindings": [{"bindingId":"BINDING_UUID","envPrefix":""}]
```

Only that component receives the managed Secret and a lease-port egress rule.
An optional prefix such as `PRIMARY_` prefixes the provider's variable names.
Conflicting names/duplicate bindings are rejected. New production deployments
have no implicit `database` Secret or project-wide PostgreSQL egress. The sample
renderer requires `--binding-id` for its web component. Update old declarations
and recreate the setup; no legacy migration/compatibility path is provided.
Legacy grant and non-expiring credential issuance endpoints now return HTTP 410.
Historical inspection/revocation remains available for operator cleanup.

Application and human writers share a resource-scoped schema owner, so they can
manage each other's tables/indexes and future schemas. They do not own the
PostgreSQL database, cannot purge it, manage global roles or install extensions.
Readers receive future-object access without data/schema write rights. An
operator-owned event trigger prevents data identities from installing even
trusted extensions; extension objects live outside writer-owned schemas.

## Credential rotation and private access

Application credentials rotate every 30 days. The platform updates only the
bound components' Secrets and credential-generation markers, triggering a
controlled restart. Applications must reconnect/retry and tolerate interruption.
Old credentials are retired after verified handover, or at most one hour after
the replacement was issued. A failed rollout/retry never extends that deadline.

Human grants are separate from credential generations. In **My store access**,
register an Ed25519 public key for private SSH access. Console-only access
does not require an SSH key. Replacing the key ends
current leases. An administrator first grants read-only/read-write access to a
resource through **Data stores** or `stores grants create RESOURCE_UUID --file`.

Use `stores access me`, `stores access key --file`, `stores access issue GRANT_UUID`
and `stores access leases GRANT_UUID`. Issuance returns non-secret pending metadata.
`stores access credential CREDENTIAL_UUID` reveals only the caller's active
credential. Pending issuance returns HTTP 202; inspect the same lease again.
Never automatically repeat an issuance POST after a timeout; reconcile lease
history first. Credential output is sensitive. The portal keeps it in component
memory, outside query caches/browser persistence, and discards it on close/expiry.

Human credentials expire after 24 hours. Early renewal issues an independent
24-hour generation and retains the old one until its original expiry. Revocation,
retirement and permission changes invalidate all affected generations immediately
in the catalog. Provider cleanup completion is separately observed/retried.

Use the existing restricted SSH account/port (`platform-db`, 2222). Returned
connection instructions identify a private relay destination; the client connects
to a local forwarded port. Neither the relay nor database has a published host
port. The bastion allows forwarding only to relay ports authorized for the human's
key, never the raw PostgreSQL endpoint. Reinstall the updated bastion configuration
when rolling out the clean setup.

The relay binds PostgreSQL startup user/database to the specific credential and
resource. Borrowing another lease port cannot extend a credential's session.
It closes established connections at the lease deadline independently of the
provider cleanup worker. Catalog refresh is once per second; permission changes
close affected streams after refresh (guard checks every 250 ms). Catalog failure
fails closed for existing and new connections. API, relay and catalog availability
are therefore part of the data-access availability budget.

PostgreSQL TLS/GSS negotiation is declined inside this initial relay profile;
use SSH transport encryption for remote clients or the isolated console network.
Startup `options`, cancellation packets and protocols other than PostgreSQL 3.0
are currently rejected. Ordinary data/query traffic is opaque and not logged.
The initial relay accepts 128 concurrent connections, 20 per credential, and 512 live credential
ports (20000–20511). A human key may authorize at most 64 leases per SSH login.
No Docker socket is exposed to the API/relay.

## PostgreSQL browser console

The portal opens `/store-console/postgresql/`. pgAdmin 9.18 uses Keycloak SSO
with Authorization Code + PKCE and subject-based identities. The operator-managed
confidential client has only the exact console callback URL; it has no service
account or direct password grant. Local pgAdmin password authentication is disabled,
including the random bootstrap administrator. Console login never grants store access.

In pgAdmin, register **Host name/address** `store-access`, **Port** the credential's
`PGPORT`, **Maintenance database** `PGDATABASE`, **Username** `PGUSER`, and **SSL mode**
`Disable`. Supply your own `PGPASSWORD`. The lease relay verifies the exact
user/database and closes the backend connection at expiry, revoke or downgrade.
Renew and register/update the new lease port/user to reconnect. Password saving,
PSQL shell and shared administrator server registrations are disabled. Query
history is not persisted. User registrations/settings live in the console volume;
these disposable preferences do not authorize restored data access.

The console has no host port and joins only the internal `store-consoles` network.
Only the edge proxy and lease relay bridge that network. The edge proxy resolves
the identity domain within this network, so HTTPS discovery/JWKS/token requests
use the same trusted issuer without raw database network access. Local deployments
using private TLS authorities must install their CA into the console trust store;
certificate verification must remain enabled. Production console and IdP traffic
uses HTTPS. The SSO fixture explicitly uses disposable loopback HTTP instead.

The production PostgreSQL image builds pgvector 0.8.7 and AGE 1.8.0-rc0 from the
reviewed commits on PostgreSQL 18.6. Only AGE is globally preloaded to support
ordinary data identities; neither extension is installed in unselected databases.
TimescaleDB remains deferred and is absent from this runtime image. pgvector
objects are in the operator-owned `platform_extensions` schema. AGE uses its
operator-owned `ag_catalog`; application graphs remain resource-scoped.

## Retention and capacity

Binding/application removal revokes consumer access and retains resource data.
Resource/project retirement revokes affected access and retains data. Purge is a
separate resource action after observed retirement/access cleanup; its preview
pins UUID, owner and version. Other consumers and the shared service remain intact.
Existing project-catalog purge retains named-store ownership/consumer records and
the reserved project identity; it never implicitly purges named stores.

The initial operator PostgreSQL allocation is 16 GiB of logical reservations,
with a default 1 GiB per resource. `STORE_CAPACITY_BYTES` supplies reviewed provider
budgets. Capacity admission counts the greater of each approved allocation and its last
measured use. Stale measurements cannot guarantee current physical headroom.
These are logical admission allocations, not physical volume quotas. PostgreSQL byte enforcement is advisory; reads/cleanup remain
available, and monitoring/admission must be distinguished from a hard quota.
Platform administrators approve quota changes within operator-owned capacity.

The controller measures up to eight resources per pass, with a one-minute minimum
interval per resource. Measurement failures retain the last reading, its original
timestamp and an explicit error; unknown usage is not emitted as zero. The portal
shows these fields. The **Named data-store resources** operator dashboard and
alerts cover quota pressure, stale/unknown usage, delayed state reconciliation,
provider credential cleanup and the controller heartbeat. Byte enforcement is
reported separately from reservations; PostgreSQL remains advisory.

Read-only lab inspection on October 17 found 31,337 MiB total memory, 25,792 MiB
available and 259 GiB free on the 301 GiB root disk. Tempo's separate 3.9 GiB
filesystem had 3.6 GiB available. This is idle/current-load evidence, not simultaneous
shared-store peak, backup/restore or full-sampling capacity acceptance. No service
was changed. Keep the 8 GiB host reserve and account for configured container limits
as additional providers are introduced.

The source catalog caps 128 resources and 64 active/pending grants per resource.
Do not expand allocations or add services without measuring total host reserves,
startup/recovery/backup demand and full-sampling telemetry. Selected services
remain running; unused or retired resources do not stop their shared service.

Follow the selected encrypted off-host backup schedule: every 12 hours,
14 daily/8 weekly/6 monthly points, 24-hour RPO and four-hour RTO. Restore must
reconcile current grants and purge tombstones before enabling API/relay issuance;
restoring old catalog rows must not resurrect access or purged resources. AGE
uses protected authoritative sources, graph definitions and loaders for rebuild.
These operational procedures and recovery targets require provider-specific
verification before deployed acceptance.

## Local verification

`UV_CACHE_DIR=/tmp/uvcache uv run --project platform/app python
scripts/verify-named-postgres.py` runs against a disposable PostgreSQL container.
It verifies database separation, cross-writer DDL, future-object read rights,
read-only/foreign-resource denial, no expiry/admin escalation, session revocation,
30-day rotation/retry/deadline handling, real authentication/query/session expiry
through the relay, and isolated purge. Relay stream tests cover identity mismatch,
revocation and catalog failure. These are not live application or recovery evidence.

The opt-in live human-access drill requires a dedicated human administrator with
no existing store grants or registered key. It refuses to replace an operator's
existing key or disrupt their leases. It retains the run projects/resources and
the dedicated user's public key; revoke/delete the dedicated identity after review.

Add `NAMED_POSTGRES_IMAGE=developer-platform-postgres:18.6-vector0.8.7-age1.8.0`
and `NAMED_POSTGRES_EXTENSIONS=1` to exercise the reviewed runtime image.
`NAMED_POSTGRES_CONSOLE=1` additionally starts disposable Keycloak/pgAdmin and
uses installed Playwright Chromium to verify real SSO, scoped connection/query,
denied password saving, expiry reconnect denial and anonymous denial. It uses
loopback-only HTTP/host networking for its disposable IdP/console, not production
HTTPS/isolated-network evidence. All fixture containers and volumes are removed.

Restore now sets an explicit named-store quarantine before services start.
The API denies credential/admin changes, the relay exposes no leases, and the
worker only revokes recovered credentials until reconciliation completes. Unbound
applications can still deploy. Older snapshots do not automatically reactivate
old grants. The provider-specific reconciliation/rebuild and verified off-host
purge-intent workflow is being completed; do not manually clear this guard.
