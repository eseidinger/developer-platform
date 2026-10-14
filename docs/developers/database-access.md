# Human PostgreSQL access

Status: source implementation, October 14, 2026. Live tunnel, isolation, and
session-revocation acceptance remain in Phase 3A.

Application database credentials are not human credentials. A project
administrator grants a named OIDC human a separate read-only PostgreSQL login
and an SSH public key. The grant is scoped to the project, audited, and may be
revoked without rotating the application's password. Only `ssh-ed25519` public
keys are supported; submit the two fields before any comment.

Use a human CLI session, with automation environment credentials cleared:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/devplat-db
# grant.json contains issuer, subject, and public_key for the named human.
devplat database-access grants create --project PROJECT --file grant.json
devplat database-access grants list --project PROJECT --output json
```

The `issuer` and `subject` must match the target human's OIDC token exactly.
The grantee may inspect their own access and rotate their SQL password. The
password is returned once, so save it in a protected password manager. Do not
pass it on a command line or include it in shell history or diagnostic logs.

```bash
devplat database-access me --project PROJECT --output json
devplat database-access credential issue --project PROJECT --output json
```

The operator installs the isolated tunnel using
`ansible/install-human-database-access.yml`. It binds to `127.0.0.1:2222` by
default; an operator must choose a specific protected management address and
firewall policy before remote users can reach it. It permits only local TCP
forwarding to the configured PostgreSQL address/port, with no shell, agent,
remote forwarding, or PTY. The dynamic key lookup fails closed if the API is
unavailable. Verify the SSH host key through an independent trusted channel.

```bash
ssh -i ~/.ssh/devplat-db -N -L 127.0.0.1:15432:POSTGRES_IP:5432 \
  -p 2222 platform-db@BASTION_HOST
```

In another terminal, use the username and database returned by `me` and the
one-time credential response. Let `psql` prompt for the password, or use an
owner-only `PGPASSFILE`; avoid `PGPASSWORD` in shared process environments.

```bash
psql -h 127.0.0.1 -p 15432 -U HUMAN_USERNAME -d PROJECT_DATABASE -W
```

Access is read-only for existing and future tables in the `public` schema
created by the project database owner. Additional schemas or writers require a
separate reviewed profile. The provisioner removes PostgreSQL's default
`PUBLIC` database access for managed project databases. Revocation disables
the human SQL login and terminates its active PostgreSQL backends; it also
removes the key's SSH authorization if no other active grant uses that key.
Existing SSH tunnels may stay connected, but cannot open a usable PostgreSQL
session with a revoked role. To rotate a key, use `database-access key replace`
with a JSON object containing `public_key`.

```bash
devplat database-access grants revoke --project PROJECT \
  --issuer ISSUER --subject SUBJECT --confirm-project PROJECT
```

The API and CLI are not a database shell or an application-data export path.
The deployed foreign-project denial, credential-separation, and revocation
checks are tracked as Phase 3A acceptance.
