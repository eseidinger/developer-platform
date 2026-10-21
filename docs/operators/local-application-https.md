# Local application-to-application HTTPS

Local workloads can use managed service credentials to call another application's
protected HTTPS endpoint. This mode retains the existing application authorization
boundary and default-deny workload network policy.

## Enable and deploy

In `.env`, enable the local mode:

```dotenv
LOCAL_APPLICATION_HTTPS_ENABLED=true
LOCAL_APPLICATION_EDGE_IP=172.30.80.32
```

Keep `APPS_DOMAIN=apps.localhost` and `IDENTITY_DOMAIN=identity.localhost`, or use
other configured domains ending in `.localhost`. The gateway address must be a
distinct usable member of `PLATFORM_SUBNET`; reserve it alongside the other fixed
addresses. Inventory's `platform_network.addresses.local-application-edge`
controls the same address. The mode defaults to disabled in `.env.example` and
rejects public domains when enabled.

Validate and deploy using the existing commands:

```bash
python3 scripts/setup/configure-platform.py --check
bash scripts/up.sh
```

Bootstrap starts the private `local-application-edge` service, exports its public
CA certificate, and prepares the API's read-only workload trust bundle. The
gateway has no published host ports. Its separate CA keys remain in its private
Docker volume; only public certificates are copied to workloads. No host firewall
opening or change to `EDGE_BIND_IP` is needed. The service's memory limit is
128 MiB and its CPU limit is 0.5 cores.

## Declare outbound access on the caller

The calling component must declare both the configured identity host and the
target application's host in its `v1alpha2` declaration:

```json
{
  "outbound": [
    {"dns": "identity.localhost", "port": 443},
    {"dns": "api-provider.apps.localhost", "port": 443}
  ]
}
```

Replace `api-provider.apps.localhost` with the actual provider URL's hostname.
Put the declaration on every component that makes those calls, including private
workers or scheduled jobs. Reapply the application after changing declarations.
Do not add the gateway or platform subnet to `ALLOWED_EGRESS_CIDRS`; the scoped
local DNS exception is independent of general outbound permission.

The renderer supplies only declaring components with hostname mappings to the
gateway, TCP/443 egress, and a read-only public CA ConfigMap. It groups names that
share an address for Kubernetes server-side apply. The bundle retains system
roots and adds the local certificates; `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, and
`NODE_EXTRA_CA_CERTS` point to it. Applications must leave those variables under
platform management. Clients that ignore these variables, such as a JVM with its
own trust store, need equivalent CA configuration in the application image.
Never disable certificate or hostname verification.

Request service access from the consumer project, approve it in the provider
project with groups accepted by its bearer-token routes, and wait for active
provisioning. Use the injected `ACCESS_*` credentials to obtain a short-lived
token and call the provider's HTTPS URL. See the
[CLI service-access procedure](../developers/cli.md#worker-access-to-its-applications-public-service).

## Boundaries and operations

The gateway routes application hosts through the same protected cluster ingress
as browser traffic. On the configured identity hostname it exposes only the
platform realm's token, JWKS, and discovery endpoints. Operator API and portal
hosts, native store console hosts, identity administration, and other realms
have no route. TLS requires matching SNI and Host values.

Unbound components receive no local gateway permission, hostname aliases, or CA
mount. Direct private-subnet CIDRs, other private services, unrelated domains,
and other ports remain governed by the existing deny policy and operator
allowlists. Application group approval remains mandatory even when network and
TLS connectivity are available.

NetworkPolicy restricts IP addresses and ports, not HTTP hostnames. Local
endpoints share one gateway address, so a gateway permission is not a separate
network boundary for each application hostname. The gateway limits the exposed
services; application tokens and provider group approvals enforce access to
individual protected applications.

After rotating a gateway CA, rerun `scripts/setup/prepare-local-trust.py` and
reapply affected application declarations. The public bundle checksum changes
the pod template so workloads adopt the new trust. To disable this mode, remove
local outbound declarations and redeploy those workloads, then set the flag to
`false` and redeploy the API. Disabling new admission alone does not remove
already applied Kubernetes permissions.

## Verify

The isolated production gateway fixture needs local Docker and Python stdlib:

```bash
python3 scripts/tests/components/networking/verify-local-https.py
```

It verifies TLS and routing with permissive synthetic upstreams, so rejected
admin, console, and mismatched-host requests prove the gateway's own boundary.
The existing [hosted-access suite](validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness)
adds real managed credentials, workload-to-workload HTTPS, database persistence,
backend/egress isolation, and credential lifecycle against disposable projects.
That live suite requires its usual explicit environment confirmation and private
runner credentials. Host-side clients still need local DNS resolution and trust
for the main edge CA as described in [local installation](install-local.md).
