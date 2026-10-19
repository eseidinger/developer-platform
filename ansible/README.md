# Ansible deployment

This source-adjacent guide is the detailed playbook and variable reference. Use
the [remote installation guide](../docs/operators/install-remote.md) for the
canonical deployment sequence and post-install handoff.

Deploy the local checkout to an existing Ubuntu 22.04+ host (amd64 or arm64)
with SSH access, Python 3, systemd, and sudo privileges. Use a Linux controller
with Python, tar, and `ansible-core >= 2.16, < 2.22` (the CI range); no extra Ansible collections are needed.
The target needs internet access to download packages, binaries, and container images.

From the repository root:

```bash
python3 -m pip install 'ansible-core>=2.16,<2.22'
cp ansible/inventory.example.yml ansible/inventory.yml
# Edit the host, SSH user, domains, email, and bind address in inventory.yml.
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --ask-become-pass
```

Omit `--ask-become-pass` if using passwordless sudo. For a public deployment,
configure platform and wildcard application DNS and the host/provider firewall
before running the playbook. Allow TCP 80/443 and restrict SSH to administrators;
account for Docker's published ports. See the root README for host capacity and
network requirements. The playbook does not change the firewall.

The playbook installs Docker from its official APT repository, verifies downloaded
kubectl and k3d checksums, copies deployment sources to `/opt/developer-platform`,
generates secrets on the target, prepares the bounded Tempo filesystem, and runs
`scripts/up.sh`. The Tempo script is transferred with the new source, so it does
not need to exist on the host before deployment. The playbook then waits for the
API dependency-readiness endpoint. Bootstrap also waits for Alloy's internal
readiness health check; a restarting/unhealthy collector fails deployment rather
than being masked by API/Prometheus readiness. This does not attest log ingestion
or seven-day retention. The controller's `.env` and `.runtime` are not transferred.
Each successful deployment writes `.runtime/installation-record.json` (root-only, no secrets) with the source revision (`+dirty` if the controller checkout has uncommitted changes), host OS, Docker/Compose/k3d/kubectl versions, running Compose image references with IDs, and the non-secret deployment parameters.
The installation and runtime directories are root-only; `.env` has mode 0600.
Run manual maintenance commands with sudo from the installation directory.
kubectl is also installed at `/usr/local/bin/kubectl` for host administration.
For example, run `sudo kubectl --kubeconfig /opt/developer-platform/.runtime/admin.kubeconfig get nodes`.

Existing `.env` secrets, volumes, and project state are preserved. Inventory values
manage endpoints, registries, drift/revision limits, workload capacity admission,
egress policy and tracing (default 100% sampling and 24-hour retention). Optional structured store/network groups and the
version/bootstrap/private-access settings below manage additional non-secret
values only when supplied. Omitted optional settings preserve the remote values;
explicit empty selections clear them. The example declares defaults, so review
those values before applying it to an existing installation. Generated service
credentials are never supplied through these inventory groups. Existing clusters
are not automatically upgraded by bootstrap; selecting another K3S image is a pin
for cluster creation, not a cluster upgrade procedure.
Back up `.env`, especially `DATABASE_KEY`, as described in [operations](../docs/operators/backup-and-recovery.md).

Human PostgreSQL access is a separate opt-in installation. After the API and
generated `DATABASE_BASTION_TOKEN` are deployed, run
`ansible-playbook -i ansible/inventory.yml ansible/install-human-database-access.yml`.
The dedicated SSH daemon binds to loopback by default. Set
`platform_database_bastion_bind_ip` to a protected management-interface IPv4
address and firewall port `platform_database_bastion_port` only when remote
developer access is intended. Verify the host key and the deployed tunnel with
the [human database access guide](../docs/developers/database-access.md).

Useful inventory overrides:

| Variable | Default | Purpose |
| --- | --- | --- |
| `platform_install_dir` | `/opt/developer-platform` | Absolute target directory |
| `platform_source_dir` | Repository containing the playbook | Local checkout to deploy |
| `platform_install_docker` | `true` | Set `false` to use an existing compatible Docker installation |
| `platform_kubectl_version` | `v1.36.4` | kubectl release compatible with the default Kubernetes 1.36 cluster |
| `platform_domain` | `platform.localhost` | Platform API domain |
| `platform_apps_domain` | `apps.localhost` | Application domain suffix |
| `platform_identity_domain` | `identity.localhost` | Keycloak/OIDC issuer domain; configure its DNS to the platform host |
| `platform_tls_email` | `admin@example.com` | ACME contact email |
| `platform_edge_bind_ip` | `127.0.0.1` | Use `0.0.0.0` for public ingress |
| `platform_image_registries` | `docker.io,ghcr.io,quay.io` | Comma-separated registries the API may resolve image tags from |
| `platform_drift_scan_interval_seconds` | `300` | Seconds between background drift scans |
| `platform_revision_retention` | `25` | Revisions kept per project; older ones and their finished operations are pruned |
| `platform_capacity_admission_enabled` | `false` | Enable fail-closed host and Kubernetes request admission after reviewing combined allocations |
| `platform_capacity_reserve_cpu_millicores` | `2000` | Minimum host infrastructure CPU allocation; not an additional deduction from Kubernetes capacity |
| `platform_capacity_reserve_memory_mib` | `8192` | Minimum host infrastructure memory allocation; charged once |
| `platform_capacity_host_overhead_cpu_millicores` | `2000` | CPU allowance for OS, node processes, uncapped shared services and transient/recovery work, in addition to capped shared-service CPU allocations |
| `platform_capacity_host_overhead_memory_mib` | `1024` | Host OS/transient memory allowance in addition to shared container limits and node runtime overhead; calibrate under representative load |
| `platform_capacity_kubernetes_overhead_memory_mib` | `4096` | Memory allowance for k3s/containerd/node processes; system Pod requests are counted separately; calibrate under representative load |
| `platform_allowed_egress_cidrs` | empty | Comma-separated external CIDRs that components may request; empty denies external component egress |
| `platform_allowed_egress_ports` | empty | Comma-separated TCP ports that components may request; empty denies external component egress |

<a id="additional-deployment-options"></a>

Additional deployment options:

| Variable | Default when omitted | Purpose |
| --- | --- | --- |
| `platform_stores` | Preserve remote selection/settings | Explicit `profiles` list, `capacity_bytes` mapping and optional `neo4j` limits |
| `platform_network` | Preserve remote settings | Private IPv4 `/24` and optional fixed service-address overrides |
| `platform_search_console_network` | Preserve remote settings | Separate private IPv4 `/29` and optional console-address overrides |
| `platform_k3s_image` | Preserve remote pin | Supported `rancher/k3s:v1.35/36/37.<patch>-k3s<release>` pin, optionally with a SHA-256 digest; kubectl must be within one minor version |
| `platform_bootstrap_subject` | Preserve remote subject | Immutable Keycloak subject for initial administrator bootstrap; clearing it does not revoke existing grants |
| `platform_store_ssh_host` | Preserve remote advertisement | Reachable management hostname/IPv4; empty disables advertisement |
| `platform_database_bastion_bind_ip` | `127.0.0.1` in the separate installer | Specific IPv4 listener; wildcard binding is rejected |
| `platform_database_bastion_port` | `2222` in the separate installer | Port 1024–65535; when supplied, also manages the portal's advertised SSH port |
| `platform_trace_sample_rate` | `1.0` | Finite fraction from 0 (off) to 1 (100%); applied to the API and platform-managed application sampler configuration |
| `platform_trace_retention` | `24h` | Tempo retention as positive whole hours (maximum `999999h`); review bounded trace-disk capacity |
| `platform_bootstrap_timeout_seconds` | `3600` | Maximum build/bootstrap runtime, range 60–14400 seconds |
| `platform_readiness_timeout_seconds` | `300` | API readiness retry window, range 5–3600 seconds; probes run every five seconds |

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
provider and PostgreSQL require positive integer byte budgets. Profiles must be a
list containing only `s3`, `qdrant`, `opensearch`, `neo4j`, with no duplicates.
`profiles: []` selects PostgreSQL only. Neo4j limits apply to retained instances
platform-wide (1–64) and memory per instance (1–16 GiB). Review combined service,
workload, telemetry and recovery requirements before enabling them. Removing a
selection does not purge data or authorize bypassing resource retirement.

Network groups require `subnet` and accept an optional `addresses` mapping keyed
by Compose service name, such as `postgres`, `store-access` or `neo4j-controller`.
Unspecified addresses are derived from standard offsets in the selected subnet;
the full service list is in [the inventory renderer](filter_plugins/platform_inventory.py).
The search-console group accepts `platform-api` and `opensearch-dashboards`.
Addresses must be distinct, inside their subnet, and exclude the network, broadcast
and gateway addresses. The two subnets must not overlap. Deployment validates the
merged remote configuration before its outage and refuses to change an existing
Docker network's subnet. Choose networks before first installation; later network
migration needs a separate operator procedure. External host/VPN/Kubernetes subnet
conflicts still require review.

To advertise private access, set `platform_store_ssh_host`, an explicit non-loopback
`platform_database_bastion_bind_ip` and `platform_database_bastion_port` together.
Deploy the platform, configure the management firewall, then run the separate
`install-human-database-access.yml` playbook. It reads the actual relay address
from the deployed `.env` and refuses a port mismatch. Rerun it after changing the
relay address or listener settings. Advertising an endpoint does not install the
bastion or configure its firewall.

Dashboards are provisioned automatically. Deployment always applies the tracing
settings, defaulting to the chosen 100% sampling and 24-hour retention. Sampling
is written to `.env`; retention is rendered into the transferred Tempo YAML while
preserving the rest of its configuration. Both values are recorded in the
installation record. Existing tracing-enabled applications still need their
declarations reapplied to pick up sampler changes. Longer retention increases
trace-storage demand; the bounded Tempo filesystem is not resized automatically. Keep secrets generated on the host; use the existing
protected/Vault-backed secret files for separate operations playbooks. Backups,
alert delivery and watchdog configuration remain in their own inventories and
are not enabled by the main platform inventory.

For an existing host with Docker, prefer `platform_install_docker: false` to
avoid changing its package source. Conflicting distribution Docker packages are
not automatically removed. The existing engine must provide Compose >= 2.20.3.

Hosted-application acceptance has a separate
[`test-platform-hosted-access.yml`](test-platform-hosted-access.yml) wrapper.
It defaults to an offline plan, does not deploy the platform, and requires
explicit API-origin confirmation for live runs. Prepare the runner environment,
public digest-pinned neutral fixture, and protected operator session on the
target using the [acceptance harness procedure](../docs/operators/validation/access-and-authorization.md#neutral-hosted-application-acceptance-harness).
This suite needs a renewable human platform-administrator session on the target,
not the basic suite's controller-side test-runner JSON. Runner/fixture-only
updates can follow the [non-deploying update procedure](../docs/operators/validation/access-and-authorization.md#update-the-runner-without-redeploying-platform-services);
they do not require the Compose outage described below. EV-45 records a directly
invoked harness run, not execution of this Ansible wrapper or full gate closure.

Human PostgreSQL access has a separate
[`test-platform-human-database-access.yml`](test-platform-human-database-access.yml)
acceptance wrapper. Its default `plan` is offline. A live `run` requires an
explicit API-origin confirmation, a renewable human platform-administrator
session, a verified bastion host key, and a public digest-pinned neutral
fixture. It creates two uniquely named fixture projects, tests the tunnel and
SQL authorization/revocation, then retains the projects for explicit review
and retirement. See the [human database acceptance procedure](../docs/operators/validation/access-and-authorization.md#human-postgresql-access-acceptance-playbook).

Rerunning the playbook reapplies sources and endpoints and reconciles the running
platform. It writes the selected `platform_trace_sample_rate` to
`PLATFORM_TRACE_SAMPLE_RATE`, defaulting to `1.0` even when a previous `.env`
selected 10% sampling. Existing tracing-enabled
application declarations must be reapplied so their sampler environment changes
too; an API restart alone cannot change a running application's sampler.
An already installed `/usr/local/sbin/platform-backup` is refreshed from the
matching transferred source before the API starts. Its configuration, credentials,
schedule and verified history are retained; this does not install or enable a new
backup service. Fresh backup setup still uses the operations playbook.
After validating the transferred Compose configuration and confirming
that no backup or availability drill is active, deployment performs a controlled
full outage of the Compose services. It stops and removes their containers, but
preserves named volumes, `.env`, the k3d cluster, and the shared Docker network.
PostgreSQL starts and becomes healthy first. Bootstrap then starts Keycloak and
the Platform API (and their identity initializers) before recreating the remaining
dynamically addressed services, so monitoring and edge containers cannot claim
their fixed addresses. Address settings are validated before the outage, and
bootstrap checks live ownership before starting services and after starting k3d.
An unexpected owner is reported without secrets and is never disconnected
automatically. This is intentionally not `docker compose down`: k3d remains
attached to the shared network, so that network must not be removed. The external
watchdog can alert if the deployment exceeds its heartbeat window.

k3d installation and bootstrap run on every deployment and report changes, even
if configuration is unchanged. Bootstrap refreshes the k3d load balancer when
the Kubernetes API is stale after a Docker restart. Source extraction does not
delete obsolete remote files. Backups and the external watchdog require the
separate [operations](../docs/operators/backup-and-recovery.md) and
[watchdog](../operations/watchdog/README.md) setup.

```bash
ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

`--check` only previews host package/directory changes; source transfer, generated
configuration, and bootstrap are skipped. It is not a deployment validation on a
fresh host. After deployment, the optional `scripts/smoke.py` test creates and
retains a project; it is not run automatically.

For a fresh-install sequence covering basic users, revocable CI credentials, and
platform tests, use [Fresh deployment and basic platform tests](../docs/operators/validation/acceptance.md).
Backup, watchdog/heartbeat, and Alertmanager setup and drills remain separate
operational tracks with their own inventories and protected credentials.

The one-time `bootstrap-platform-test-runner.yml` playbook uses a human
platform-administrator token and writes the returned client credential to an
explicit mode-`0600` path on the controller. Create the protected parent directory
there first; the playbook checks that it is writable and that the output file does
not already exist before creating the one-time credential. The repeatable `test-platform.yml` playbook consumes
that protected file, creates empty disposable projects and short-lived role
personas, performs the first deployment with a project CI credential, and cleans
up without retaining the human token. `test-platform-ci-credential.yml` is the
narrower compatibility check for an already prepared project.

`test-platform-components.yml` is the Phase 2A acceptance suite. Run it with the
normal platform inventory and the protected test-runner output; it creates and
retires its own disposable project, so it needs no human token. It checks legacy
migration, two stable internal Services, a scheduled internal connectivity probe,
non-overlap, invalid-cron rejection, an isolated component update, revision
history, and component retirement scope. It deliberately does not trigger or
inspect backup storage: backup evidence remains a separate operational track.
It also checks the authorized component-log search and polling-cursor contract;
That endpoint's Kubernetes log retention remains best effort. PLAN-017 adds a
separate authorized retained-log endpoint for minimized centralized operational
events, configured for seven days. Its deployed and elapsed-retention checks
are separate from this component suite.

`revoke-platform-test-runner.yml` removes exactly one active named runner. Supply
`platform_api_url` and a fresh human platform-administrator token; the runner JSON
and credential ID are not needed. It defaults to `platform-acceptance-suite`; set
`platform_test_runner_name` for another runner and set
`platform_confirm_test_runner_revocation` to that same name. The playbook refuses
no or ambiguous active matches, revokes Platform API access before provider cleanup,
and polls until cleanup is complete.

`verify-platform-test-runner-expiry.yml` is a two-stage, scheduled-safe expiry
drill for a dedicated one-day test runner: run it once with
`platform_expiry_drill_phase=active`, then schedule the same protected credential
file after its recorded expiry with `platform_expiry_drill_phase=expired`.
The following Phase 2C playbooks create and retire their own disposable projects.
They consume the protected test-runner file; no reusable human or project token is
accepted:

```bash
# Named-store rollback check; supply a published digest-pinned web/PostgreSQL image.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-rollback-data.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_rollback_drill_host=platform \
  -e platform_rollback_drill_image=REGISTRY/web-postgres@sha256:DIGEST

# Temporarily enable and exercise reserved-capacity admission, then restore policy.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-capacity-admission.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_capacity_drill=true \
  -e platform_capacity_drill_acknowledgement=I_ACCEPT_CAPACITY_DRILL

# Uses a temporary, exact 1.1.1.1/32:853 allow-list and restores the prior
# Platform API environment during cleanup.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-egress-policy.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_egress_drill=true \
  -e platform_egress_drill_acknowledgement=I_ACCEPT_EGRESS_DRILL

# Optional: override all three defaults with a reachable listener you control.
# This replacement is also temporary and is restored during cleanup.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-egress-policy.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_allow_egress_drill=true \
  -e platform_egress_drill_acknowledgement=I_ACCEPT_EGRESS_DRILL \
  -e platform_egress_target_host=198.51.100.10 \
  -e platform_egress_target_cidr=198.51.100.10/32 \
  -e platform_egress_target_port=8443

# Controlled shared Keycloak outage; the always block restores the service.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-identity-provider-outage.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_identity_drill_host=platform \
  -e platform_allow_identity_outage_drill=true \
  -e platform_identity_outage_acknowledgement=I_ACCEPT_IDENTITY_OUTAGE

# Disposable application plus shared proxy/Prometheus failure and recovery signals.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-failure-signals.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_failure_drill_host=platform \
  -e platform_allow_failure_signal_drill=true \
  -e platform_failure_drill_acknowledgement=I_ACCEPT_FAILURE_SIGNAL_DRILL
```

The capacity drill reads the API's request-accounting snapshot, creates a temporary
restricted namespace containing one synthetic pod request, and automatically leaves
less than 100m CPU or 128Mi memory available. It proves the fixed workload is rejected,
removes the reservation, and then proves the same-sized real workload is admitted.
It preserves the exact host `.env`, temporarily enables admission with a valid zero reserve,
recreates only `platform-api`, and restores the original `.env` and API container in an
`always` block. The reservation namespace is also always removed.
Normal deployments manage admission enablement and budgets through the
`platform_capacity_*` inventory variables above. The drill deliberately overrides
the minimum reserve only for its duration; shared-service allocations and overhead
allowances still apply. It restores the exact pre-drill environment afterward.
The egress drill defaults to [Cloudflare's public DNS-over-TLS listener](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-tls/)
at `1.1.1.1:853`. It replaces the two Platform API allow-list variables and temporarily
disables capacity admission only for the drill, recreates only `platform-api`, and restores
the exact original `.env` and API container in its `always` cleanup. Override all three target variables together when
that endpoint is not reachable from workload pods. Never retain or broaden a normal
production allow-list merely to pass the drill.

The PostgreSQL, Keycloak, capacity, and failure-signal drills intentionally disrupt shared services and
must not run in routine CI. The rollback-data helper now creates a named
PostgreSQL resource and checks persistence through its bound workload; a live
rerun is still required.
`scripts/isolation.py`, `scripts/data_preservation.py`, and
`scripts/interrupted_provisioning.py` now use run-scoped named PostgreSQL
resources and the web/PostgreSQL fixture, but await live runs. The interruption
drill pauses the shared k3d server and kills the Platform API; it requires an
otherwise idle lab and is not a routine acceptance check.
The historical passes do not validate the current binding contract. The
human-access harness now uses named resources and expiring credentials; its full live rerun remains separate from the
older implicit-database evidence. Egress alters only a disposable workload but depends on operator policy
and an external listener. Keep these drills in an explicitly approved protected pipeline
rather than pull-request CI.

The failure-signal drill also temporarily disables capacity admission so its disposable
canary tests only application, ingress, and monitoring signals. It restores the exact
host `.env` and recreates `platform-api` in its `always` cleanup.

Installation references: [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
and [kubectl on Linux](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/).

See [watchdog deployment](../operations/watchdog/ansible/README.md) and [heartbeat deployment](../operations/heartbeat/README.md).

## Backups

See [backup setup and scheduling](../operations/backup/README.md).

## Alertmanager email

See [inventory-based SMTP setup and delivery checks](../operations/alertmanager/README.md).
