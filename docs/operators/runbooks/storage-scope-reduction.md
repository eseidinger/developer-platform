# PLAN-039 storage scope reduction: operator record

Use this record with the [delivery plan](../../maintainers/delivery/plans/storage-scope-reduction.md)
for each installation. PostgreSQL and S3 remain the project data stores.
OpenSearch, Qdrant, Neo4j, CouchDB, and HugeGraph remain available only for
existing-resource migration and retirement until their data and backup gates
are complete. The separate storage lab is outside this platform rollout.

## Inventory before changing services

Record the deployed Git revision, host, Compose project, selected profiles,
control database snapshot identifier, and time. Run the following query on the
`platform` control database with an operator read role. Its transaction is
read-only. Save the result in restricted operator evidence; it includes project,
resource, and component names but no credential values or application data.

```sql
BEGIN READ ONLY;

SELECT r.resource_id, r.owner_project, r.name, r.provider,
       r.state, r.observed_state, r.error_code, r.version,
       r.quota_bytes, r.used_bytes, r.purge_backup_version,
       count(DISTINCT g.grant_id) FILTER (
           WHERE g.state IN ('pending', 'active')) AS live_grants,
       count(DISTINCT c.credential_id) FILTER (
           WHERE c.state <> 'revoked' AND c.expires_at > now()
       ) AS live_credentials,
       string_agg(DISTINCT g.consumer_project || '/' || g.component, ', ')
           FILTER (WHERE g.kind = 'binding' AND g.state IN ('pending', 'active'))
           AS bound_components
FROM store_resources AS r
LEFT JOIN store_grants AS g ON g.resource_id = r.resource_id
LEFT JOIN store_credentials AS c ON c.grant_id = g.grant_id
WHERE r.provider IN ('opensearch', 'qdrant', 'neo4j', 'couchdb', 'hugegraph')
GROUP BY r.resource_id
ORDER BY r.provider, r.owner_project, r.name;

COMMIT;
```

Include `purged` rows to preserve the history and identify backup retention.
For each row, add the data owner, dependent application, authoritative or
rebuildable status, retention deadline, proposed destination, migration plan,
verification method, and disposition. Resolve resources outside selected
Compose profiles as well as resources with `PurgeAwaitingVerifiedBackup`.

Inventory provider containers, Neo4j instances, named and anonymous volumes,
routes, native consoles, monitoring targets, secrets, and encrypted backup
contents. Use Compose labels to distinguish this platform from other projects
on the same host. Record identifiers and retention requirements, never secret
values. An absent container does not prove that its volume or data is absent.

For the CPU/RAM baseline, record the time, workload identity and demand,
observability settings, host CPU and RAM, service reservations, and observed
usage. Capture at least one representative steady period with the same
measurement method to be repeated after shutdown. `docker stats --no-stream`
gives a point sample; retain the time series or repeat samples for a comparison.
Do not sum process or container RSS and call it available host memory.

## Freeze and cutover

Deploy the creation freeze after confirming that existing resources still
appear in the API and can be retired. Check direct create requests for all five
removed providers: each must return validation failure before a catalog insert
or native call. Check PostgreSQL and S3 creation, extension selection,
bindings, human leases, and supported consoles with disposable resources.

For each authoritative resource, obtain its application owner's cutover and
recovery plan. Verify an encrypted off-host backup before changing a binding or
credential. Move data to PostgreSQL or S3, check application behavior and
counts or checksums, then retire the old resource. A rebuildable projection
needs a verified input and rebuild procedure. PLAN-040 extensions are not a
PLAN-039 migration prerequisite.

Use the resource-specific purge preview and confirmation only after the owner
and retention decision. Wait for the exact purge intent to appear in a verified
backup and for the worker to report `purged`. Confirm grant, lease, Secret,
route, and console-session revocation. Keep the old service and protected data
when a check fails.

## Provider shutdown gate

For each provider, record an empty set of resources requiring native access,
including pending purges and retained resources, and a version-pinned restore
route for backups kept through their retention period. Only then remove its
runtime path and selected service in a controlled rollout. Compare the volume
inventory with backup evidence before deleting a volume. Check retained-store
health throughout.

Repeat the CPU/RAM measurement with comparable workload demand and telemetry.
Record removed reservations, observed service use, host reserve, and workload
headroom before and after. Explain any gap between expected and measured gain.
PLAN-039 is complete only when every resource, service, backup, and volume has
a recorded disposition and the retained-store and capacity checks pass.
