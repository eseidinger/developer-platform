# Named data-store resources

Phase 7 implementation is in progress. PostgreSQL named resources, the API/CLI,
portal and private lease relay are implemented in source and disposable tests.
Provider expansion, browser-console deployment, backup/restore and deployed
acceptance are still being completed. No existing installation has been reset.

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
register an Ed25519 public key before issuing credentials. Replacing the key ends
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

## Retention and capacity

Binding/application removal revokes consumer access and retains resource data.
Resource/project retirement revokes affected access and retains data. Purge is a
separate resource action after observed retirement/access cleanup; its preview
pins UUID, owner and version. Other consumers and the shared service remain intact.
Existing project-catalog purge retains named-store ownership/consumer records and
the reserved project identity; it never implicitly purges named stores.

The initial operator PostgreSQL allocation is 16 GiB of logical reservations,
with a default 1 GiB per resource. `STORE_CAPACITY_BYTES` supplies reviewed provider
budgets. These are admission allocations, not measured host capacity or physical
volume quotas. PostgreSQL byte enforcement is advisory; reads/cleanup remain
available, and monitoring/admission must be distinguished from a hard quota.
Platform administrators approve quota changes within operator-owned capacity.

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
