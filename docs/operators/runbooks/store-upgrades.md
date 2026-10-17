# Shared PostgreSQL upgrades

Upgrades are operator-triggered maintenance. Application credentials still rotate
on their normal schedule; consumers must tolerate interruption and reconnect or
restart. A store image change does not grant permission to reset its volume.

Before changing the installation, record the source revision, running image ID,
PostgreSQL major/minor version, installed extension versions in every named
resource database, target image ID/digest and release notes. Inspect host memory,
disk and the 8 GiB host reserve, including concurrent backup/recovery demand.
Build the target image from reviewed source/extension pins. Moving a tag is not a
reviewed upgrade.

Run the version-specific compatibility matrix and named-resource recovery
fixture locally before maintenance. The recovery fixture can restore the current
source image's encrypted backup into the candidate image:

```bash
NAMED_POSTGRES_IMAGE=REVIEWED_SOURCE_IMAGE \
NAMED_POSTGRES_RECOVERY_IMAGE=REVIEWED_TARGET_IMAGE \
NAMED_POSTGRES_EXTENSIONS=1 \
RESTIC_TEST_BINARY=/path/to/restic \
uv run --project platform/app python scripts/verify-named-postgres.py
```

The fixture checks actual SQL/catalog restoration into an empty temporary server,
restore quarantine, all recovered credential/grant revocations, latest purge
intent, protected AGE graph rebuild, retained SQL/pgvector data and fresh explicit
read-only approval. Preserve the exact image IDs and output as release-specific
evidence. This small local fixture does not measure deployed recovery throughput
or establish application reconnection and the four-hour RTO.

Take a new encrypted off-host backup using the installed backup job before the
upgrade. Confirm its readback verification, snapshot ID and capture time in the
job's private status record, and verify repository access and recovery keys.
Retain that snapshot and the previous image. A recent-looking job timestamp alone
does not prove recoverability. Do not continue after a backup/compatibility error.

Describe the maintenance impact before starting: PostgreSQL and its applications
can be unavailable until service and data checks pass. Pause new administrative
changes. Deploy matching API, backup/recovery scripts, identity/relay/console
configuration and pinned PostgreSQL image together using the established
[installation procedure](../../../ansible/README.md). That procedure causes a
controlled Compose outage and preserves volumes. Never use `down --volumes`.
For a PostgreSQL major-version change, prepare and validate a supported logical
restore or `pg_upgrade` procedure; never mount an existing data directory under a
different major version and assume compatibility.

`CREATE EXTENSION IF NOT EXISTS` does not upgrade an installed extension. Inspect
installed and available versions after the server starts. Apply only reviewed,
release-supported extension upgrade SQL as the operator, for each selected
resource; data credentials cannot run `ALTER EXTENSION`. If the release requires
rebuilding a projection or restoring a database, follow its tested procedure.
Do not silently run extension migrations from the lifecycle controller.

Verify PostgreSQL/API readiness, each resource's selected extensions, scoped
reader/writer schema and data queries, graph/vector queries, and a bound
application's reconnection or controlled restart. Exercise both private and
console access, expiry/revocation and pending application-credential handover.
Its one-hour old-generation deadline must remain unchanged across the outage;
an expired generation requires recovery with current credentials, not an extended
lease. Check store/telemetry dashboards and backup health, then record the target
revision, image IDs, checks, interruption and recovery time.

If verification fails, keep affected access closed and preserve diagnostics
privately. An older binary may not read migrated data or extension catalogs;
rollback requires the release-tested recovery route and verified pre-upgrade
backup, not merely selecting the old tag. Restore quarantine revokes recovered
store grants; fresh explicit approval and bindings follow validation. In-place
replacement/deletion of real data requires separately authorized destructive
recovery; this runbook does not authorize it.
