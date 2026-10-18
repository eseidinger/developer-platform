# Human access to named stores

Status: source implementation with disposable PostgreSQL/pgAdmin acceptance,
October 17, 2026. Live rollout and deployed recovery acceptance remain open.

A project administrator creates an independent resource and explicitly grants a
human read-only or read-write access. Platform administrators have those management
powers across projects, but need their own human grant for direct data access.
Application bindings use separate credentials. Removing an application retains data.

Use **Data stores** in the project portal for resource/grant administration and
**My store access** for your own leases and connection details. Personal credential
operations require an interactive `platform-cli` or `platform-portal` login;
automation tokens are not human identities, including unregistered service clients.

For terminal workflows:

```bash
# An administrator creates grant.json with issuer, subject and mode.
devplat stores grants create RESOURCE_UUID --file grant.json
devplat stores grants list RESOURCE_UUID --output json
# The named human uses their own interactive CLI profile.
devplat stores access me --output json
devplat stores access issue GRANT_UUID --output json
devplat stores access leases GRANT_UUID --output json
devplat stores access credential CREDENTIAL_UUID --output json
```

Use the current resource/grant UUIDs. Issuance returns pending metadata; inspect
the same credential UUID until ready. Never repeat an issuance POST automatically
after a timeout: inspect lease history first. Only the named human can reveal an
active credential, including during its original 24-hour validity. Early renewal
creates another independent 24-hour lease and does not extend the old one.
Permission changes, revocation and retirement invalidate affected generations.

For private SSH access, register an Ed25519 key using
`devplat stores access key --file key.json`, with `{"public_key":"ssh-ed25519 ..."}`.
Replacing a key ends your current leases. Register the key before issuing the
lease you want to use. The operator must configure a reachable private bastion;
the default installer listens on loopback. Independently verify the bastion's SSH
host key and place it in a `known_hosts` file. Then open a local PostgreSQL tunnel
with the active credential UUID:

```bash
devplat stores access tunnel CREDENTIAL_UUID \
  --identity-file ~/.ssh/id_ed25519 \
  --known-hosts ~/.ssh/known_hosts \
  --local-port 15432
```

The command runs in the foreground; Ctrl-C closes the local tunnel. It requires
an owner-only private key file, verifies the bastion against the supplied
`known_hosts` file, and forwards only to `127.0.0.1` on your machine. The key
may forward only to your credential's private relay ports, with no shell, agent,
remote forwarding or PTY. If the credential is still issuing, inspect it again
before opening the tunnel. If the bastion is not configured, the command reports
that no reachable SSH bastion is available.

After starting the tunnel, connect the native PostgreSQL client to its **local**
forwarded address/port, using `PGUSER`/`PGDATABASE` from your lease. Let the client
prompt for its password or use an owner-only `PGPASSFILE`. The relay closes the
existing database connection at expiry; a still-open SSH tunnel does not extend it.
An empty advertised SSH host means the operator has not configured remote access.

For browser access, open the console link in **My store access**, sign in to
pgAdmin with your platform identity, and register host `store-access`, the lease's
`PGPORT`, maintenance database `PGDATABASE`, username `PGUSER`, SSL mode `Disable`,
and your own `PGPASSWORD`. Raw database ports stay private. Password saving is
disabled. Renew and reconnect with the new lease port/username at expiry.

Both application and human read-write access include application-schema
create/alter/drop. Readers have existing/future table access. Server administration,
extension installation, access grants/default ACL changes and security-definer
routines remain operator privileges. Shared writer ownership permits startup
migrations and changes to other approved writers' tables in the same resource.

Revoke through the portal or `stores grants revoke GRANT_UUID --file version.json`,
where the file contains the current `version`. Revocation retains data and affects
every credential generation. Resource purge is a separate confirmed action after
retirement and cleanup, waiting for verified off-host purge intent before deletion.
The old implicit-project `database-access` issuance commands now return HTTP 410.

See the [resource, rotation and recovery workflow](../operators/data-stores.md)
and [rebuildable AGE example](../../examples/postgresql-graph/README.md).
