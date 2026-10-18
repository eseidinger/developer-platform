# Named data-store resources

Phase 7 implementation is in progress. PostgreSQL named resources, the API/CLI,
portal and private lease relay are implemented in source and disposable tests.
The pinned AGE/pgvector image and pgAdmin SSO configuration are in source.
Disposable console SSO/connection and encrypted empty-server restore fixtures pass;
RustFS, OpenSearch, Qdrant and dedicated Neo4j Community have native providers and opt-in service selection
with local isolation/recovery evidence. RustFS, Qdrant and OpenSearch Dashboards
browser access, plus Neo4j Browser, pass local native-login, supported-mode/isolation
and expiry/revocation fixtures; deployed acceptance remains incomplete. No existing installation has been reset.

An October 18 node-01 manual check passed private SSH/Bolt access, invalid-password
denial and HTTPS console launch/session boundaries for one existing Neo4j human
lease after the restricted bastion was updated.
See [EV-51](../maintainers/delivery/backlog.md#verification-register) for the
exact repair and limits; this does not close deployed provider acceptance.

A subsequent October 18 node-01 PostgreSQL check created two active named
resources in `data-store-test`. Private bastion access passed writer DDL/data,
read-only denial, wrong-password and cross-resource denial. Downgrading a writer
closed its held session; a new read-only lease read retained data but could not
write. The pgAdmin entry returned its login page; authenticated console use,
application binding and deployed recovery remain open. The resources and marker
were retained for follow-up. See [EV-52](../maintainers/delivery/backlog.md#verification-register).

The same lab then deployed bound `web` and unbound `probe` test components.
Only `web` received a scoped PostgreSQL Secret and relay egress. Its credential
read and wrote the assigned resource through an operator tunnel. Revoking the
binding closed its SQL session and removed the Secret and egress rule while both
components remained ready. The test workload does not issue SQL itself; see
[EV-53](../maintainers/delivery/backlog.md#verification-register).

Short-lived service-account test personas then checked cross-project PostgreSQL
binding approval on node-01. Separate owner and consumer project administrators
exercised pending request, denied consumer approval, owner approval, scoped
read-only native access, and consumer revocation; a viewer was denied resource
management. All personas were revoked and the disposable consumer project was
retired. These personas cannot exercise personal human leases or pgAdmin SSO.
See [EV-54](../maintainers/delivery/backlog.md#verification-register).

The October 18 follow-up exercised SQL inside a disposable pod using the bound
component's managed Secret and relay-only egress. A controlled 30-day rotation
closed a held SQL session, delivered a fresh credential and allowed a new pod
to reconnect and read/write retained data. Revocation removed the Secret and
egress rule; the retained test application was restored to an unbound spec.
A Kubernetes field-manager conflict exposed by the first rollout was corrected
and a second bind/rotation/reapply/revocation cycle passed without deleting the
Deployment. See [EV-58 and EV-59](../maintainers/delivery/backlog.md#verification-register).

Deployed pgAdmin browser automation then passed real portal/console OIDC sign-in,
read-only scoped connection and query, password-save denial, other-human and
anonymous isolation, and denied reconnect after grant revocation. The disposable
Keycloak users and grant were removed/revoked. Natural 24-hour lease expiry and
a separate read-write console user remain untested; see
[EV-60](../maintainers/delivery/backlog.md#verification-register).

An October 18 read-only node-01 monitoring check found both named PostgreSQL
resource databases in deployed size series. All 27 PostgreSQL dashboard queries
parsed against live Prometheus, with 26 returning data; the unlimited database
connection-limit panel was empty as expected. The exporter reported `pg_up=1`
and no scrape error, and Grafana's provisioned dashboard files matched source.
See [EV-62](../maintainers/delivery/backlog.md#verification-register).

## Selecting shared services

For remote deployments, configure the optional `platform_stores` group in the
[Ansible inventory](../../ansible/inventory.example.yml): `profiles` is a list,
`capacity_bytes` is a mapping, and `neo4j` holds optional instance/memory limits.
The [deployment playbook](../../ansible/deploy.yml) validates and writes these
settings before its outage, preserving generated secrets. Omit the group to retain
existing remote settings; `profiles: []` explicitly selects PostgreSQL only.
See the [inventory option reference](../../ansible/README.md#additional-deployment-options).

Run `python3 scripts/init.py` to generate missing operator keys without replacing
existing keys. After reviewing combined host capacity, set `COMPOSE_PROFILES` in
the operator `.env` to the desired comma-separated services: `s3`, `qdrant`,
`opensearch`, `neo4j`. An empty selection keeps PostgreSQL only. Explicitly allocate each
selected provider in `STORE_CAPACITY_BYTES`, for example:

```dotenv
COMPOSE_PROFILES=s3,qdrant,opensearch,neo4j
STORE_CAPACITY_BYTES={"postgresql":17179869184,"s3":8589934592,"qdrant":4294967296,"opensearch":4294967296,"neo4j":4294967296}
```

These are example logical allocations, requiring review against physical capacity.
Compose limits are 1 GiB/one CPU each for RustFS and Qdrant, and 2 GiB/two CPUs
for OpenSearch, plus a transient 512 MiB initializer. Existing services, workload
requests, telemetry, backup and recovery also need headroom. Services remain
running together; removing a selection does not remove or purge their volumes.
Disable selection only during coordinated operator maintenance after revoking
access; it is not a substitute for retirement or purge.

Use the existing operator deployment workflow or `bash scripts/up.sh` to prepare
configuration, start the selected services and wait for health/initialization.
Ansible prepares configuration before the existing maintenance outage. The API
advertises a provider only when selection, required configuration and a positive
capacity allocation are present. This reports configuration readiness; native
provisioning/reconciliation reports actual service failures separately. Neo4j
Community Edition uses the selected
[dedicated-instance model](../maintainers/delivery/plans/data-store-expansion.md#neo4j-community-dedicated-instance-decision):
one Docker instance/volume per named resource, initially one retained resource per
project, with explicit full instance access only. Read-only grants are rejected.
The `neo4j` selection requires its operator controller/key and capacity budget;
configuration readiness does not establish deployed acceptance.

`scripts/prepare-stores.py` generates an operator-owned OpenSearch CA, verified
server/client certificates and a non-demo access realm under `.runtime/stores`.
Only the public CA is mounted into the API/relay. The unprivileged one-shot
initializer alone receives the administrator client key; it retains an existing
native access catalog and refuses to overwrite a damaged one. Repeat preparation
preserves keys. Address changes, partial configuration or certificates with less
than one day remaining require explicit operator repair/renewal before deployment.
Node/admin certificates expire after one year; the CA expires after ten years.
Generated certificates include explicit CA/leaf constraints, key usage and key
identifiers for strict TLS verification in the production Python runtime.
Legacy profiles are refused before deployment until explicitly renewed:

```bash
cd /opt/developer-platform
sudo python3 scripts/prepare-stores.py --renew-opensearch-certificates
sudo docker compose up -d --no-deps --force-recreate --wait --wait-timeout 240 opensearch
```

Renewal preserves the CA, node and administrator private keys, subjects, native
identities and data. It stages and strictly verifies the complete public chain
before replacing certificates and refreshing the mounted public CA. Recreate the
OpenSearch container to load the new files; its named volume is retained. Confirm
API native collection and scoped queries after restart. Keep the previous public
chain with the pre-maintenance configuration backup.
Keep those configuration files in the encrypted recovery bundle. No provider has
a raw published host port; the API has native administrative credentials and no
Docker socket. This source wiring does not constitute deployed acceptance.

## Dedicated Neo4j Community resources

Selecting `neo4j` builds the reviewed Community image from
`persistence/neo4j/Dockerfile`. Creating a named resource then provisions its own
persistent container, volume and internal network. Resource UUIDs determine names;
renaming the resource does not recreate data. The project limit includes retired
resources until confirmed purge. Several components, including owner-approved
cross-project consumers, may bind to that same instance.

The `neo4j-controller` is an operator service with Docker socket authority; neither
the API, relay, project application nor console receives that socket. The controller
accepts bounded predefined operations from the fixed API source using
`NEO4J_CONTROLLER_KEY`; it accepts no arbitrary image, mount, command or Cypher.
Only the controller receives `NEO4J_ADMIN_KEY`, used to derive separate per-instance
native administrator passwords. Rotating the RPC key does not change those native
passwords. Preserve the admin key in the encrypted configuration backup; changing
it requires reviewed native administrator credential maintenance.

Default limits are four retained instances across the platform, one CPU and
1.5 GiB memory per instance. Configure `NEO4J_MAX_INSTANCES` (1–64) and
`NEO4J_INSTANCE_MEMORY_BYTES` (1–16 GiB) only after reviewing combined host capacity,
including the 8 GiB reserve, shared stores, Kubernetes workloads and recovery.
Instance count admission includes retained stopped resources; byte quotas remain
advisory. Memory/image changes for existing instances require reviewed operator
maintenance. Native instances have no published host ports, Docker socket or
unrestricted procedure plugins; file-URL CSV imports are disabled.

Each instance network admits only its server and the API/relay/controller
infrastructure. Every five seconds the operator controller reconciles attachments
after Compose replaces infrastructure containers. This changes connectivity only;
it never starts a stopped instance or reactivates a grant. The local network fixture
verifies replacement IDs rejoin correctly and stopped instances remain stopped.

The wire/API mode `read-write` means **full instance access** for Community,
including data/schema changes and native account management. Provider/resource
responses explicitly expose `capabilities.access_model=full-instance`,
`supported_modes=[read-write]` and the project limit. Read-only requests and
read-only downgrades fail. Keep explicit human grants, component bindings and owner
approval; platform administration alone still grants no native data access.
Full-access users can disrupt other users or the administrator within this same
resource. Account mutations cannot create a platform lease or extend its deadline:
relay admission independently verifies the issued platform secret. Account cleanup
failures remain visible while revoked access is fenced. Retirement can stop the
instance, and confirmed purge can remove its owned volume/network, even when its
native administrator password was changed. Repairing active native administration
requires isolated operator maintenance, not broader project/platform privileges.

Applications receive `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` and
`NEO4J_DATABASE=neo4j`. Use the direct `bolt://` endpoint through the private relay
or encrypted SSH tunnel; native Bolt TLS is disabled inside that private boundary
so authentication cannot hide in an opaque stream. The relay negotiates reviewed
Bolt 5.4, checks every LOGON/reauthentication, rejects impersonation, and closes
held connections at lease expiry, revocation or stale catalog state. Chunk large
imports: client messages are bounded to 1 MiB and 16 concurrent Bolt connections
across the relay, within its existing total connection budget. Queries are forwarded
unchanged; Cypher text is not used as an authorization filter.

Use **Open Neo4j console** on an active human credential. In official Neo4j Browser,
choose `bolt+s://`, enter the console hostname with port `443` as the Connection
URL, and enter this lease's `NEO4J_USERNAME`/`NEO4J_PASSWORD`. The portal session
cookie authorizes the frontend; native authentication still applies. WSS transports
Bolt to the same private relay and accepts only the matching console Origin and
lease. Already-open sockets close on expiry/revocation. Invalid reloads clear the
console's cookies/storage; saved local values belong to that browser profile.
Use trusted HTTPS in deployment; fixture certificates and ignored browser errors
are disposable-test choices.

Scheduled backup pauses leases and captures the stopped native `/data` volume,
including the system database, with an image inventory in the encrypted bundle.
The original instance must restart after capture. Restore requires empty volumes,
reviewed matching image inventory, quarantine, recovered-identity cleanup and fresh
approval. It rebuilds private endpoints rather than reusing old addresses; retired
resources return to their stopped state. Update the installed backup runner before
enabling this provider. A tag downgrade is not a validated recovery procedure.
See the [compatibility evidence](../../persistence/compatibility/neo4j-2026-10-17.md).

## Resource and binding workflow

Follow the [shared-store upgrade runbook](runbooks/store-upgrades.md) for reviewed
image/extension changes and the release-specific encrypted recovery fixture.

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
Credential logins do not inherit schema authority after `SET ROLE NONE`; normal
connections use the shared resource role. New functions have no PUBLIC execute
grant. Data writers cannot change grants/default ACLs or create security-definer
routines; those are operator privileges. This preserves managed read-only access
while ordinary application-schema create/alter/drop remains available.
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

Use the existing restricted SSH account/port (`platform-db`, 2222). The bastion
installer defaults to loopback. For remote native access, configure its deliberate
listener with `platform_database_bastion_bind_ip`/`platform_database_bastion_port`,
then set `STORE_SSH_HOST`/`STORE_SSH_PORT` to the reachable matching entry point.
An empty host omits remote SSH instructions; it never guesses that the public
platform hostname has a reachable SSH service. Browser access remains available.
Returned
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
ports (20000–20511). A human can hold at most 64 current credential leases across resources, matching
the SSH key authorization limit. Each grant also caps outstanding generations at 24.
No Docker socket is exposed to the API/relay.

For HTTP stores, use the returned SSH forwarding instructions and replace only
the host/port in `AWS_ENDPOINT_URL_S3`, `QDRANT_URL` or `OPENSEARCH_URL` with
`http://127.0.0.1:15432` on your local client. Keep the resource identifier and
scoped credential unchanged. S3 clients must use path-style addressing. OpenSearch
uses Basic authentication, Qdrant its JWT API key and RustFS its S3 service key.
The outer relay binds requests to that lease identity, streams bounded chunks
and closes connections at expiry/revocation. OpenSearch backend TLS remains
verified with the operator CA; private HTTP on the tunnel/relay segment relies
on SSH transport encryption. Applications receive the private lease endpoint
directly through their explicit binding. Supported console adapters advertise browser launch links for active human credentials.

## DuckDB/Parquet application artifacts

The [application example](../../examples/analytics-artifacts/README.md) uses bound
S3 credentials to publish exact-version Parquet manifests and stream/checksum
snapshots before local DuckDB queries. No additional shared service or API runtime
dependency is introduced. Back up application reference metadata as well as the
retained bucket versions. Logical snapshot immutability does not prevent an
authorized writer from deleting versions; recovery still requires the encrypted
bucket/catalog backups and fresh access approval. Synthetic SQL comparisons and
empty-volume snapshot recovery pass locally; external domain benchmarks and
deployed off-host recovery remain open.

## RustFS, Qdrant and OpenSearch browser consoles

Use the provider's **Open console** action on an active human credential.
The portal posts a 30-second launch assertion to a lease hostname under the existing
`APPS_DOMAIN`; it never puts a credential in a launch URL. The gateway sets a
Secure, HttpOnly, host-only session cookie bounded by the human lease deadline.
Sign in to the Qdrant Web UI using your `QDRANT_API_KEY`, or to RustFS Key Login
using `RUSTFS_CONSOLE_ACCESS_KEY` and `RUSTFS_CONSOLE_SECRET_KEY`.
RustFS uses a separate human-only, bucket-scoped IAM identity for the official
console's native STS exchange. Child access keys and token hashes are bound to the
exact human generation before login completes; no child secret/token is stored
in the platform catalog. Applications and private native clients continue to
use expiring service-account keys. The gateway
checks the current human grant/generation for every request; native data requests
still use the matching native human credential through the private relay. Native
data requests never use an operator key.
A platform administrator still needs an explicit human grant. Static assets and
backend data become unavailable after expiry, downgrade, retirement or revocation;
renew and launch a fresh session to continue.

The API proxies at most 32 concurrent console requests with bounded streaming.
Only fixed operator endpoints and the selected lease port are reachable. Writes
require the exact console Origin; cross-origin response sharing, WebSockets and
upgrades are rejected. Only the dedicated encrypted Dashboards authentication
cookie is forwarded to that provider; the platform launch cookie stays private. This adapter's verified UI path uses ordinary
HTTP requests. Each launch and an invalidated session clear the console site's
browser storage/cache; server responses are not cached. The native UI can save
its key in browser storage during the active session, so clear site data when
finishing on a shared browser. The platform cookie is not exposed to the provider.
Raw URL access logging is disabled in the API image; traces retain route/status
metadata without native queries, headers, bodies or credentials.

The existing Caddy edge routes `console-20000` through `console-20511` hostnames
under `APPS_DOMAIN` to this gateway. On-demand certificates require a current human
lease on that port. Verify wildcard application DNS, trusted HTTPS and certificate
issuance capacity before deployed acceptance; new lease hostnames also consume
issuer rate limits. A local real-browser fixture uses a synthetic TLS certificate
and controlled portal launch; it does not accept deployed DNS/OIDC/TLS or recovery.

RustFS console assets are built into the API image from source v0.1.37 at the
checksum-verified commit in `platform/consoles/rustfs.json`. The upstream
permission-refresh loop is fixed by the one-line `patch-rustfs.cjs`; this keeps
an authorized page mounted while policy refreshes, preserving initial and native
authorization checks. The image includes the Apache-2.0 license and modification
notice. No browser-time downloads or updates occur. A console lists only its
catalog-authorized bucket; this metadata adapter grants no global bucket-list
permission. All object operations remain native-authorized.

### OpenSearch Dashboards

Sign in with the issued `OPENSEARCH_USERNAME` and `OPENSEARCH_PASSWORD`. Create
an index pattern matching `OPENSEARCH_INDEX`, select it in Discover and browse
that resource's documents. Read-only grants cannot write documents or mappings;
both modes may edit console preferences and saved views. The workspace belongs
to the resource and is shared with its explicitly granted humans. It persists
across credential renewal; global and private per-user tenants are disabled.
Console indexes contribute to resource usage and are captured with the native
volume backup. Confirmed purge removes the resource's data index, tenant and
physical console indexes while retaining other resources.

Dashboards 3.9.0 uses a separate internal `search-consoles` network with the API.
It has no host port, raw-store network membership or administrator key.
`STORE_SEARCH_CONSOLE_SUBNET`, `STORE_SEARCH_API_IP` and
`OPENSEARCH_DASHBOARDS_IP` must be distinct from platform/cluster networks;
bootstrap validates fixed members and existing owners. Run `scripts/init.py` to
generate the separate missing `STORE_OPENSEARCH_CONSOLE_COOKIE_KEY` without
replacing existing secrets. The native cookie is Secure, HttpOnly, host-only and
bounded by the original human deadline. Renewal requires a new launch/login.

The private bridge requires the fixed console source IP and binds native Basic
identity, tenant and relay port to the active human generation. Its restricted
`kibanaserver` account handles global system metadata and the exact pre-login
settings read; it cannot read resource documents or administer identities.
Resource metadata migrations and searches run as the leased human. Unbound
server calls cannot select resource tenants/indexes, including through bulk
payloads; server-metadata writes are bounded to 1 MiB. Native backend TLS uses
the generated operator CA with certificate verification enabled. The gateway
preserves the upstream content security policy and adds its own boundary.

The reviewed native tenant policy is `resource-v1`. Preparation rejects older
cached policies rather than silently reusing them; migrate existing realms only
through reviewed operator maintenance. Credential issuance requires private
native tenants disabled. Keep native and UI multitenancy enabled with only the
named resource tenant available; disabling UI multitenancy produces incorrect
saved-object mappings in this pinned release. The local browser fixture verifies
Discover, both data-access modes, cross-resource denial, workspace renewal,
expiry/revocation and isolated purge. Deployed OIDC, DNS, trusted TLS, off-host
recovery and upgrade acceptance remain open. See the
[compatibility record](../../persistence/compatibility/opensearch-2026-10-17.md).

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
Do not copy `PGHOST` into pgAdmin: that private relay IP is unreachable from
the isolated console network. An October 18 node-01 user-confirmed connection
using `store-access` is recorded in [EV-55](../maintainers/delivery/backlog.md#verification-register).
The portal now displays the pgAdmin host and the private native-client `PGHOST`
in separate labelled sections; the [live UI correction](../maintainers/delivery/backlog.md#verification-register)
is recorded as EV-56.
Renew and register/update the new lease port/user to reconnect. Password saving,
PSQL shell and shared administrator server registrations are disabled. SQL query history is bounded to 20 entries per user/database in the console
volume; it is not a platform telemetry export. User registrations/settings live in the console volume;
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

## AGE authoritative snapshots and rebuild

Use the [scoped snapshot loader/example](../../examples/postgresql-graph/README.md)
for durable AGE projections. Complete source snapshots, stable source keys,
explicit labels and reviewed GIN/source-key index definitions are stored in an
operator-owned append-only table inside the resource database. Writers may append
sources but cannot change/delete history. A server-generated ordinal orders
versions; clock changes cannot select an older snapshot as latest. The helper and
recovery path bound each resource to 64 graph identities and read one source at
a time. Each source is bounded to eight MiB, 10,000 vertices, 50,000 edges and
64 labels/index definitions. These are operational limits, not adoption gates.

Root recovery validates all source checksums before replacing graphs, using AGE's
normal graph/label APIs. It restores source-defined indexes/constraints and scoped
ownership. AGE internal IDs are rebuilt; external references must use stable
source keys. Native Cypher edits, labels and indexes must also be represented in
protected sources/definitions to survive recovery. Arbitrary SQL dependencies on
generated graph objects require separate protected loaders; the generic loader
refuses to cascade into them. Unregistered retained graphs fail backup preflight.

The real local [dump/restore and rebuild evidence](../../persistence/compatibility/projection-rebuild-2026-10-17.md)
covers two graphs, multiple labels, a cycle, updated/escaped properties, declared
indexes, readers and preserved ordinary SQL/pgvector data. It closes the local
source-rebuild implementation gap; deployed recovery/reconnection and RPO/RTO
acceptance remain open.

## Retention and capacity

Shared-store backup adapters now capture retained RustFS, Qdrant and OpenSearch
volumes, including native access metadata, with the SQL catalog. For a bundle
containing non-PostgreSQL resources, capture holds the lifecycle lock and sets a
35-minute bounded lease pause. The relay closes managed access, and the backup
terminates only named-resource PostgreSQL credential sessions before capturing
data. Shared services stop for volume capture and restart using persisted recovery
instructions, while managed leases stay paused until the SQL dump completes.
Application credential clocks continue throughout. Applications must tolerate
this scheduled maintenance interruption and reconnect/retry afterward.

These guarantees cover platform-managed lease paths. Operators must pause their
own direct administrative writers; the platform cannot coordinate external data
access that bypasses its resource contract. PostgreSQL-only bundles retain their
existing online logical-dump behavior. A pause clears on ordinary capture failure
and expires after 35 minutes on a hard interruption; loss of the held snapshot
connection fails the backup instead of verifying a partially quiesced capture.
Restores require each retained provider's matching archive and restore its volume
before startup/quarantine reconciliation. Generated operator store configuration
under `.runtime/stores` is included in the encrypted source bundle when present.

Local fixtures pass a real stopped-volume capture and empty-volume restore for
all three native providers, including retained data/schema/native access metadata,
recovered-key revocation and fresh scoped approval. The real PostgreSQL fixture
also verifies relay denial, termination of a held managed SQL session, preservation
of the control connection and pause cleanup after interruption. This is not a
deployed coordinated multi-store restore or off-host throughput/RPO/RTO acceptance.

Binding/application removal revokes consumer access and retains resource data.
Resource/project retirement revokes affected access and retains data. Purge is a
separate resource action after observed retirement/access cleanup; its preview
pins UUID, owner and version. Accepted purge requests wait in `purging` with
`PurgeAwaitingVerifiedBackup` until the scheduled backup captures their intent,
uploads it encrypted off-host and verifies readback. Only then does the backup job
acknowledge that exact resource version/snapshot, allowing the worker to delete
its data. Operators may run the existing backup job early. Backup failure leaves
data retained and access revoked; retries never bypass verification. Install the
updated backup job together with this source before using purge. Other consumers and the shared service remain intact.
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

Neo4j checks run only against disposable services:

```bash
docker build -t developer-platform-neo4j:2026.09.0-community-jmx1.6.0 persistence/neo4j
uv run --project platform/app python scripts/verify-neo4j-catalog.py
uv run --project platform/app python scripts/verify-neo4j-network-recreation.py
NEO4J_CONSOLE_FIXTURE=1 uv run --project platform/app python scripts/verify-neo4j.py
```

The browser fixture additionally needs the portal's installed Playwright Chromium.
It verifies native access and schemas, independent admission, held-session fencing,
empty-volume recovery, network isolation, official Browser login and resource purge.
The [performance monitoring guide](../../infrastructure/monitoring/README.md#phase-7-store-performance)
links all eight dashboards, native pipeline verification and workload instrumentation.


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
old grants. Restore reads the latest verified `store-recovery.json` from the
configured off-host repository even when an older data snapshot was selected.
Its hash must match the verified bundle manifest. Every recovered generation is
revoked in the provider; every recovered grant is revoked. Latest purging/purged
UUIDs are deleted again, retired resources remain retained, and surviving data
must pass provider validation. A data snapshot missing a newer retained resource
is refused instead of silently creating an empty database.

The guarded operator command is `python -m app.stores.recovery --manifest-sha256
SHA256 [--apply]` inside the API container, with the verified manifest on stdin.
Without `--apply` it reviews the plan. The restore script uses this command before
project reapply and requires fresh owner approval/new binding declarations for
store consumers. It never reactivates old grants for a transparent restart.
Do not manually clear the guard. AGE graph-OID/query validation keeps recovery
closed until its authoritative projection rebuild succeeds. Source-only fixtures
do not satisfy the four-hour deployed recovery target.

Set `RESTIC_TEST_BINARY` to an installed restic executable when running the named
PostgreSQL fixture to exercise an encrypted **local intent-only** repository:
verification before purge, latest-intent replay after a simulated older catalog/data
restore, all-grant revocation, and fresh approval before access. This does not use
the real off-host repository, send notifications or demonstrate a full data restore.
The backup suite also exercises real encrypted roundtrip/retention locally.
Database dumping and intent capture hold the shared lifecycle lock. Application
data queries and relay expiry checks continue, while resource/grant/deployment
mutations wait. The lock is released on interruption and has a bounded idle timeout;
a lost lock makes the capture fail instead of verifying an inconsistent point.

Personal credential issuance requires an end-user token issued to the platform portal or CLI, plus the caller’s explicit human grant. Service-account administration does not confer personal store access. Each human can hold at most 64 current private-access leases; each grant allows at most 24 outstanding generations.

Project retirement confirmation pins named resource and grant versions. The platform commits the store access fence before requesting namespace deletion. After a partial retirement, request a fresh preview before retrying; the portal refreshes it when namespace deletion is still in progress. Data remains retained throughout. Recovery operators must review platform/project administrative roles against current authority before releasing quarantine; restoring store data never reactivates recovered data grants.
