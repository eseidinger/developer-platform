# Web + PostgreSQL starter

This source template is a small public Python web service backed by the
independently managed named PostgreSQL resource through an approved read-write
binding for component `web`. The platform injects `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`; do not add database passwords
to the image or declaration. The app emits only status-coded structured logs.
Public ingress is **denied until a separate hosted-access policy is active**.

From the repository root, with a human CLI profile and a public image registry:

```bash
docker build -t REGISTRY/web-postgres:1 examples/web-postgres
docker push REGISTRY/web-postgres:1
# Obtain the registry-reported sha256 digest for that pushed image.
devplat projects create --project demo
# Create a named PostgreSQL resource and a read-write binding for component web.
# Wait for both observed states to be active; use the returned binding UUID.
python3 examples/web-postgres/render.py --project demo --image REGISTRY/web-postgres@sha256:DIGEST \
  --binding-id BINDING_UUID > application.json
devplat deploy apply --project demo --file application.json --wait
devplat components list --project demo --output json
devplat stores list --project demo --output json
```

`DIGEST` means the actual 64-character hexadecimal image digest. Use a unique
project slug and replace `REGISTRY` with a public registry under your control.
The renderer rejects mutable tags and requires `--binding-id`. See the
[named-resource workflow](../../docs/operators/data-stores.md) to create the resource
and binding. Unbound components receive no database credentials. `projects create` requires platform authority;
if the project exists, skip it. The named project owner or administrator needs
deployment permission. The declaration uses bounded resource requests and an
HTTP readiness check that queries PostgreSQL.

To enable browser access, the project administrator creates group `readers`
and applies [access-policy.json](access-policy.json), replacing the group name
with its returned stable ID if preferred:

```bash
devplat access groups create --project demo --name readers --display-name Readers \
  --idempotency-key demo-readers --output json
devplat access policy apply --project demo --application demo \
  --file examples/web-postgres/access-policy.json --wait
```

An authorized human must then complete the hosted application's first-login
request and receive group assignment; a platform role alone never permits
application traffic. The policy allows authenticated browser GET requests only.
Read `/` and `/api/visits` at `https://web-demo.<apps-domain>` to see the page
and persistent visit counter. Do not use this sample for sensitive data.

For a reproducible diagnosis, generate a second declaration with `--fail-ready`
and apply it using the current revision's `--if-match` value. The container
remains running but `/health/ready` returns 503. Inspect:

```bash
devplat components list --project demo --output json
devplat operations get OPERATION_ID --output json
devplat logs --project demo --component web --tail 50 --output json
devplat drift --project demo --output json
```

Regenerate without `--fail-ready` and apply with the current revision to
recover. This is a source-level journey; deployed acceptance and the injected
failure, role matrix, and UI/API compatibility checks are Phase 9 anytime work.

| Identity | Project create | Deploy/diagnose | Manage hosted policy | Read app |
| --- | --- | --- | --- | --- |
| Platform administrator | Yes | Yes | Yes | Only with `readers` membership |
| Project administrator | No | Yes | Yes | Only with `readers` membership |
| Project developer | No | Yes | No | Only with `readers` membership |
| Project viewer | No | Read-only diagnosis | No | Only with `readers` membership |
| Deployment credential | No | Scoped deploy/diagnose | No | No implicit access |
| Unrelated principal | No | No | No | No |

The matrix is the intended authorization contract, not a claim that the
deployed role/denial matrix has passed; see Phase 9 acceptance.
