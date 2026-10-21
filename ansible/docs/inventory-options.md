# Inventory options

Back to the [Ansible directory guide](../README.md). Run commands from the
repository root.

Existing `.env` secrets, volumes, and project state are preserved. Inventory
values manage endpoints, registries, drift/revision limits, workload capacity
admission, egress policy and tracing (default 100% sampling and 24-hour
retention). Optional structured store/network groups and the
version/bootstrap/private-access settings below manage additional non-secret
values only when supplied. Omitted optional settings preserve the remote values;
explicit empty selections clear them. The example declares defaults, so review
those values before applying it to an existing installation. Generated service
credentials are never supplied through these inventory groups. Existing clusters
are not automatically upgraded by bootstrap; selecting another K3S image is a
pin for cluster creation, not a cluster upgrade procedure. Back up `.env`,
especially `DATABASE_KEY`, as described in
[operations](../../docs/operators/backup-and-recovery.md).

Human PostgreSQL access is a separate opt-in installation. After the API and
generated `DATABASE_BASTION_TOKEN` are deployed, run
`ansible-playbook -i ansible/inventory.yml ansible/operations/install-human-database-access.yml`.
The dedicated SSH daemon binds to loopback by default. Set
`platform_database_bastion_bind_ip` to a protected management-interface IPv4
address and firewall port `platform_database_bastion_port` only when remote
developer access is intended. Verify the host key and the deployed tunnel with
the [human database access guide](../../docs/developers/database-access.md).

## Common inventory overrides

- **`platform_install_dir`**
  - **Default:** `/opt/developer-platform`
  - **Purpose:** Absolute target directory
- **`platform_source_dir`**
  - **Default:** Repository containing the playbook
  - **Purpose:** Local checkout to deploy
- **`platform_install_docker`**
  - **Default:** `true`
  - **Purpose:** Set `false` to use an existing compatible Docker installation
- **`platform_kubectl_version`**
  - **Default:** `v1.36.4`
  - **Purpose:** kubectl release compatible with the default Kubernetes 1.36
    cluster
- **`platform_domain`**
  - **Default:** `platform.localhost`
  - **Purpose:** Platform API domain
- **`platform_apps_domain`**
  - **Default:** `apps.localhost`
  - **Purpose:** Application domain suffix
- **`platform_identity_domain`**
  - **Default:** `identity.localhost`
  - **Purpose:** Keycloak/OIDC issuer domain; configure its DNS to the platform
    host
- **`platform_tls_email`**
  - **Default:** `admin@example.com`
  - **Purpose:** ACME contact email
- **`platform_edge_bind_ip`**
  - **Default:** `127.0.0.1`
  - **Purpose:** Use `0.0.0.0` for public ingress
- **`platform_image_registries`**
  - **Default:** `docker.io,ghcr.io,quay.io`
  - **Purpose:** Comma-separated registries the API may resolve image tags from
- **`platform_drift_scan_interval_seconds`**
  - **Default:** `300`
  - **Purpose:** Seconds between background drift scans
- **`platform_revision_retention`**
  - **Default:** `25`
  - **Purpose:** Revisions kept per project; older ones and their finished
    operations are pruned
- **`platform_capacity_admission_enabled`**
  - **Default:** `false`
  - **Purpose:** Enable fail-closed host and Kubernetes request admission after
    reviewing combined allocations
- **`platform_capacity_reserve_cpu_millicores`**
  - **Default:** `2000`
  - **Purpose:** Minimum host infrastructure CPU allocation; not an additional
    deduction from Kubernetes capacity
- **`platform_capacity_reserve_memory_mib`**
  - **Default:** `8192`
  - **Purpose:** Minimum host infrastructure memory allocation; charged once
- **`platform_capacity_host_overhead_cpu_millicores`**
  - **Default:** `2000`
  - **Purpose:** CPU allowance for OS, node processes, uncapped shared services
    and transient/recovery work, in addition to capped shared-service CPU
    allocations
- **`platform_capacity_host_overhead_memory_mib`**
  - **Default:** `1024`
  - **Purpose:** Host OS/transient memory allowance in addition to shared
    container limits and node runtime overhead; calibrate under representative
    load
- **`platform_capacity_kubernetes_overhead_memory_mib`**
  - **Default:** `4096`
  - **Purpose:** Memory allowance for k3s/containerd/node processes; system Pod
    requests are counted separately; calibrate under representative load
- **`platform_allowed_egress_cidrs`**
  - **Default:** empty
  - **Purpose:** Comma-separated external CIDRs that components may request;
    empty denies external component egress
- **`platform_allowed_egress_ports`**
  - **Default:** empty
  - **Purpose:** Comma-separated TCP ports that components may request; empty
    denies external component egress

## Additional deployment options

- **`platform_stores`**
  - **Default when omitted:** Preserve remote selection/settings
  - **Purpose:** Explicit `profiles` list, `capacity_bytes` mapping and optional
    `neo4j` limits
- **`platform_network`**
  - **Default when omitted:** Preserve remote settings
  - **Purpose:** Private IPv4 `/24` and optional fixed service-address overrides
- **`platform_search_console_network`**
  - **Default when omitted:** Preserve remote settings
  - **Purpose:** Separate private IPv4 `/29` and optional console-address
    overrides
- **`platform_k3s_image`**
  - **Default when omitted:** Preserve remote pin
  - **Purpose:** Supported `rancher/k3s:v1.35/36/37.<patch>-k3s<release>` pin,
    optionally with a SHA-256 digest; kubectl must be within one minor version
- **`platform_bootstrap_subject`**
  - **Default when omitted:** Preserve remote subject
  - **Purpose:** Immutable Keycloak subject for initial administrator bootstrap;
    clearing it does not revoke existing grants
- **`platform_store_ssh_host`**
  - **Default when omitted:** Preserve remote advertisement
  - **Purpose:** Reachable management hostname/IPv4; empty disables
    advertisement
- **`platform_database_bastion_bind_ip`**
  - **Default when omitted:** `127.0.0.1` in the separate installer
  - **Purpose:** Specific IPv4 listener; wildcard binding is rejected
- **`platform_database_bastion_port`**
  - **Default when omitted:** `2222` in the separate installer
  - **Purpose:** Port 1024–65535; when supplied, also manages the portal's
    advertised SSH port
- **`platform_trace_sample_rate`**
  - **Default when omitted:** `1.0`
  - **Purpose:** Finite fraction from 0 (off) to 1 (100%); applied to the API
    and platform-managed application sampler configuration
- **`platform_trace_retention`**
  - **Default when omitted:** `24h`
  - **Purpose:** Tempo retention as positive whole hours (maximum `999999h`);
    review bounded trace-disk capacity
- **`platform_bootstrap_timeout_seconds`**
  - **Default when omitted:** `3600`
  - **Purpose:** Maximum build/bootstrap runtime, range 60–14400 seconds
- **`platform_readiness_timeout_seconds`**
  - **Default when omitted:** `300`
  - **Purpose:** API readiness retry window, range 5–3600 seconds; probes run
    every five seconds

For example, select all optional providers with explicit data budgets:

```yaml
platform_stores:
  profiles: [s3, qdrant, opensearch, neo4j]
  capacity_bytes:
    postgresql: 17179869184
    s3: 8589934592
    qdrant: 4294967296
    opensearch: 4294967296
    neo4j: 4294967296
  neo4j:
    max_instances: 4
    memory_bytes: 1610612736
```

These are example data allocations, not a host sizing guarantee. Every selected
provider and PostgreSQL require positive integer byte budgets. Profiles must be
a list containing only `s3`, `qdrant`, `opensearch`, `neo4j`, with no
duplicates. `profiles: []` selects PostgreSQL only. Neo4j limits apply to
retained instances platform-wide (1–64) and memory per instance (1–16 GiB).
Review combined service, workload, telemetry and recovery requirements before
enabling them. Removing a selection does not purge data or authorize bypassing
resource retirement.

Network groups require `subnet` and accept an optional `addresses` mapping keyed
by Compose service name, such as `postgres`, `store-access` or
`neo4j-controller`. Unspecified addresses are derived from standard offsets in
the selected subnet; the full service list is in
[the inventory renderer](../filter_plugins/platform_inventory.py). The
search-console group accepts `platform-api` and `opensearch-dashboards`.
Addresses must be distinct, inside their subnet, and exclude the network,
broadcast and gateway addresses. The two subnets must not overlap. Deployment
validates the merged remote configuration before its outage and refuses to
change an existing Docker network's subnet. Choose networks before first
installation; later network migration needs a separate operator procedure.
External host/VPN/Kubernetes subnet conflicts still require review.

To advertise private access, set `platform_store_ssh_host`, an explicit
non-loopback `platform_database_bastion_bind_ip` and
`platform_database_bastion_port` together. Deploy the platform, configure the
management firewall, then run the separate `install-human-database-access.yml`
playbook. It reads the actual relay address from the deployed `.env` and refuses
a port mismatch. Rerun it after changing the relay address or listener settings.
Advertising an endpoint does not install the bastion or configure its firewall.

Dashboards are provisioned automatically. Deployment always applies the tracing
settings, defaulting to the chosen 100% sampling and 24-hour retention. Sampling
is written to `.env`; retention is rendered into the transferred Tempo YAML
while preserving the rest of its configuration. Both values are recorded in the
installation record. Existing tracing-enabled applications still need their
declarations reapplied to pick up sampler changes. Longer retention increases
trace-storage demand; the bounded Tempo filesystem is not resized automatically.
Keep secrets generated on the host; use the existing protected/Vault-backed
secret files for separate operations playbooks. Backups, alert delivery and
watchdog configuration remain in their own inventories and are not enabled by
the main platform inventory.

For an existing host with Docker, prefer `platform_install_docker: false` to
avoid changing its package source. Conflicting distribution Docker packages are
not automatically removed. The existing engine must provide Compose >= 2.20.3.
