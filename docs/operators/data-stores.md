# Named data-store resources

The platform offers named PostgreSQL databases and optional S3-compatible object
storage through RustFS. PostgreSQL resources can select extensions installed in
the reviewed server image. The retired OpenSearch, Qdrant, Neo4j, CouchDB, and
HugeGraph providers are recorded in the
[PLAN-039 cutover evidence](validation/storage-scope-2026-11-12.md) and the
[historical backlog](../maintainers/delivery/backlog.md). Their pre-removal
implementation is pinned at Git commit `632b921` for recovery of older snapshots.

## Selecting shared services

PostgreSQL is always installed. Select RustFS only when an application needs S3.
In the [Ansible inventory](../../ansible/inventory.example.yml), set
`platform_stores.profiles: [s3]` and allocate positive `capacity_bytes` for both
providers. A local installation uses the same settings in `.env`:

```dotenv
COMPOSE_PROFILES=s3
STORE_CAPACITY_BYTES={"postgresql":17179869184,"s3":8589934592}
```

These are logical admission budgets, not disk quotas or host resource
reservations. Review PostgreSQL, RustFS, tracing, backups, workload requests,
and the host reserve together. An empty profile list selects PostgreSQL only.
Run `python3 scripts/init.py` for missing credentials, then use the normal
[deployment playbook](../../ansible/deploy.yml) or local `bash scripts/up.sh`.
The API advertises S3 only when selected, configured, and allocated capacity.
Removing a profile never purges a resource or its backup.

## Resource and binding workflow

A project administrator creates a resource owned by that project. Platform
administrators can manage resources across projects; data access still requires
a grant. A PostgreSQL create file can contain:

```json
{"name":"primary","provider":"postgresql","quota_bytes":1073741824,"extensions":[]}
```

For S3, use `"provider":"s3"` and an empty `extensions` list. Submit with
`devplat stores create --project NAME --file resource.json`. Wait for
`observed_state=active` in `devplat stores get RESOURCE_UUID`. The resource UUID
identifies the database or bucket even if its display name changes. PostgreSQL
extensions must already exist in the operator-installed image.

The reviewed PostgreSQL extension selections are `vector` (pgvector), `age`,
`timescaledb`, `postgis`, `pgmq`, and `pg_duckdb`. For example:

```json
{"name":"events","provider":"postgresql","quota_bytes":1073741824,"extensions":["timescaledb","postgis","pgmq"]}
```

Installation occurs in a fixed operator-controlled order. A project writer
cannot create, drop, or upgrade extensions. pgmq queue functions mutate queue
state, so queue use is reserved for writers. `pg_duckdb` execution is reserved
for writers of resources selecting it; local files, network URLs, and S3 are
disabled in DuckDB SQL. Applications needing S3 use a separately granted S3
resource and its scoped credentials.

Request component access with
`devplat stores bindings request --project NAME --file binding.json`:

```json
{"resource_id":"RESOURCE_UUID","component":"web","mode":"read-write"}
```

A same-project administrator's request is approved; cross-project requests need
approval from the owning project's administrator or a platform administrator.
Only an active approved binding supplies a managed Secret and lease-port egress
to that component. Add the resulting binding ID to its v1alpha2 specification:

```json
"bindings": [{"bindingId":"BINDING_UUID","envPrefix":""}]
```

An optional `envPrefix` separates variables from multiple bindings. Revocation
removes the Secret and egress rule. PostgreSQL writers can manage their resource
schema but cannot install extensions, administer the server, or purge the
database. Readers receive read access to future objects without schema or data
write rights.

## Credential rotation and private access

Application credentials rotate every 30 days. The old generation remains valid
only during bounded handover, at most one hour. Applications should reconnect
and retry after a rotation or scheduled backup pause. A failed rollout cannot
extend the old generation's deadline.

A human needs an explicit resource grant. In **My store access**, register an
Ed25519 key for private SSH access, then issue a credential for the grant. The
portal and CLI show the issued secret only to the owning human. Human
credentials expire after 24 hours; early renewal creates a separate generation.
Revocation, retirement, mode changes, and key replacement close affected relay
sessions. The restricted bastion forwards only to lease ports, never directly to
PostgreSQL or RustFS. The relay fails closed on catalog failure.

Use the returned SSH tunnel instructions for native PostgreSQL or S3 clients.
For S3, replace only the endpoint host and port with the local forwarded port,
keep the scoped key, and use path-style bucket addressing. PostgreSQL startup
binds the database and login to the selected lease; S3 HTTP requests must carry
a signature from the matching key. Neither relay logs query text, object paths,
headers, bodies, or credentials.

## S3 browser console

Use **Open console** on an active S3 human credential. The portal posts a short
launch assertion to the lease hostname; the gateway then sets a secure,
HTTP-only cookie bounded by the human lease. Sign in to RustFS Key Login with
`RUSTFS_CONSOLE_ACCESS_KEY` and `RUSTFS_CONSOLE_SECRET_KEY` from that credential.
The console uses a bucket-scoped native identity and a child STS session tied to
the same human generation. Every object request still passes native S3
authorization through the lease relay. The gateway does not grant global bucket
listing or administrator access. Revocation, expiry, downgrade, or retirement
requires a new grant and launch before access can resume.

The RustFS console assets are pinned in `platform/consoles/rustfs.json` and
packaged with the API image. The gateway rejects cross-origin writes, WebSocket
upgrades, and access outside its fixed private endpoint and selected relay port.

## PostgreSQL browser console

The pgAdmin browser console uses the portal's SSO and a scoped human PostgreSQL
lease. Its connection is limited to the named database and current grant mode.
Saving a database password is disabled. A revoked or expired grant denies a new
connection and closes an active one. The console itself has no server-wide
administration grant. See the
[PostgreSQL verification record](../maintainers/delivery/backlog.md#verification-register)
for the exercised browser paths and their limits.

## AGE authoritative snapshots and rebuild

If an application uses AGE as a projection, retain its authoritative source,
loader, graph definition, and a validation procedure. Restore keeps access
quarantined until the graph and source agree. The
[AGE operations guide](../maintainers/delivery/plans/data-store-expansion.md)
contains the historical verification context. The four-extension expansion is
tracked separately in [PLAN-040](../maintainers/delivery/plans/postgresql-extension-expansion.md).

## Retention and capacity

The scheduled encrypted off-host backup captures PostgreSQL, the control
catalog, application Secrets, the selected RustFS volume, and the versioned
store recovery manifest. A backup with retained S3 resources pauses managed
leases for at most 35 minutes and stops RustFS briefly for volume capture.
Operators must pause direct administrative writers outside the lease contract.
PostgreSQL-only backups use online logical dumps.

Resource retirement revokes access but retains data. Purge is a separate action
after observed retirement and credential cleanup. Its preview pins UUID, owner,
and version. An accepted purge waits for an uploaded and read-back-verified
backup containing that exact intent. The worker then purges native data and
preserves catalog tombstones, audit records, and backup history. A failed backup
keeps the resource in the pending purge state.

The controller measures up to eight resource usages per pass, retaining the
last successful reading with its timestamp after an error. Admission counts the
greater of approved quota and last measured use. PostgreSQL byte quota is
advisory. The named-store dashboard separates usage, quota, freshness, hard
quota support, reconciliation, credential cleanup, and controller heartbeat.
The catalog caps 128 resources and 64 active or pending grants per resource.

Recovery loads the latest verified intent, revokes recovered generations, and
requires fresh approval before issuing access. A pre-purge snapshot must not
resurrect purged resources. Historical snapshots containing live removed-provider
data require the pinned pre-removal commit `632b921` on an isolated recovery host;
the current restore refuses them before mutating the host. See the
[backup runbook](backup-and-recovery.md) and the
[PLAN-039 operator record](runbooks/storage-scope-reduction.md).

## Local verification

Run the PostgreSQL component fixture against a disposable database and the
application, CLI, backup, and UI test suites before a controlled deployment.
For PLAN-040, also run
`scripts/tests/components/stores/verify-postgres-extension-expansion.py`
against the reviewed image. It tests all selectable extension subsets and the
managed writer/reader contract. The
[PLAN-040 evidence](validation/postgresql-extensions-2026-11-12.md) records
the chosen versions, creation-order requirement, and remaining deployment
gates.
The fixture covers isolation, grants, rotation, read-only permissions, and
recovery quarantine. The S3 console and relay tests cover signed identity,
scoped browser access, revocation, and expiry. Compare deployed CPU and RAM
under representative workloads using the
[PLAN-039 evidence record](validation/storage-scope-2026-11-12.md).
