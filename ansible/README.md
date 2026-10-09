# Ansible deployment

This source-adjacent guide is the detailed playbook and variable reference. Use
the [remote installation guide](../docs/operators/install-remote.md) for the
canonical deployment sequence and post-install handoff.

Deploy the local checkout to an existing Ubuntu 22.04+ host (amd64 or arm64)
with SSH access, Python 3, systemd, and sudo privileges. Use a Linux controller
with Python, tar, and `ansible-core >= 2.16`; no extra Ansible collections are needed.
The target needs internet access to download packages, binaries, and container images.

From the repository root:

```bash
python3 -m pip install 'ansible-core>=2.16'
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
generates secrets on the target, and runs `scripts/up.sh`. It then waits for the
API dependency-readiness endpoint. The controller's `.env` and `.runtime` are not transferred.
Each successful deployment writes `.runtime/installation-record.json` (root-only, no secrets) with the source revision (`+dirty` if the controller checkout has uncommitted changes), host OS, Docker/Compose/k3d/kubectl versions, running Compose image references with IDs, and the non-secret deployment parameters.
The installation and runtime directories are root-only; `.env` has mode 0600.
Run manual maintenance commands with sudo from the installation directory.
kubectl is also installed at `/usr/local/bin/kubectl` for host administration.
For example, run `sudo kubectl --kubeconfig /opt/developer-platform/.runtime/admin.kubeconfig get nodes`.

Existing `.env` secrets, volumes, and project state are preserved. Inventory values
manage only `PLATFORM_DOMAIN`, `APPS_DOMAIN`, `IDENTITY_DOMAIN`, `TLS_EMAIL`, and `EDGE_BIND_IP`.
Other settings retain their generated or existing values. For a custom subnet or
K3S image, prepare the target `.env` using `scripts/init.py` and edit it before the
first deployment. Existing clusters are not automatically upgraded by bootstrap.
Back up `.env`, especially `DATABASE_KEY`, as described in [operations](../docs/operators/backup-and-recovery.md).

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
| `platform_capacity_admission_enabled` | `false` | Enable fail-closed aggregate Kubernetes request admission after measuring the host and choosing reserves |
| `platform_capacity_reserve_cpu_millicores` | `2000` | CPU excluded from workload admission accounting for the platform and operating margin |
| `platform_capacity_reserve_memory_mib` | `8192` | Memory excluded from workload admission accounting for the platform and operating margin |
| `platform_allowed_egress_cidrs` | empty | Comma-separated external CIDRs that components may request; empty denies external component egress |
| `platform_allowed_egress_ports` | empty | Comma-separated TCP ports that components may request; empty denies external component egress |

For an existing host with Docker, prefer `platform_install_docker: false` to
avoid changing its package source. Conflicting distribution Docker packages are
not automatically removed. The existing engine must provide Compose >= 2.20.3.

Rerunning the playbook reapplies sources and endpoints and reconciles the running
platform. After validating the transferred Compose configuration and confirming
that no backup or availability drill is active, deployment performs a controlled
full outage of the Compose services. It stops and removes their containers, but
preserves named volumes, `.env`, the k3d cluster, and the shared Docker network.
PostgreSQL starts and becomes healthy before the dynamically addressed services
are recreated. This is intentionally not `docker compose down`: k3d remains
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
Kubernetes log retention remains explicitly best effort.

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
# Application rollback retains PostgreSQL contents and the current secret version.
ansible-playbook -i ansible/inventory.yml ansible/test-platform-rollback-data.yml \
  -e @~/.local/state/developer-platform/platform-test-runner.json \
  -e platform_rollback_drill_host=platform

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
Normal deployments manage the admission enablement and reserves through the three
`platform_capacity_*` inventory variables above. The drill deliberately overrides
them only for its duration and restores the exact pre-drill environment afterward.
The egress drill defaults to [Cloudflare's public DNS-over-TLS listener](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-tls/)
at `1.1.1.1:853`. It replaces the two Platform API allow-list variables and temporarily
disables capacity admission only for the drill, recreates only `platform-api`, and restores
the exact original `.env` and API container in its `always` cleanup. Override all three target variables together when
that endpoint is not reachable from workload pods. Never retain or broaden a normal
production allow-list merely to pass the drill.

The PostgreSQL, Keycloak, capacity, and failure-signal drills intentionally disrupt shared services and
must not run in routine CI. The rollback drill is safe for a protected acceptance
environment. Egress alters only a disposable workload but depends on operator policy
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
