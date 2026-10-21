# Deployment reference

Back to the [Ansible directory guide](../README.md). Run commands from the
repository root.

This source-adjacent guide is the detailed playbook and variable reference. Use
the [remote installation guide](../../docs/operators/install-remote.md) for the
canonical deployment sequence and post-install handoff.

Deploy the local checkout to an existing Ubuntu 22.04+ host (amd64 or arm64)
with SSH access, Python 3, systemd, and sudo privileges. Use a Linux controller
with Python, tar, and `ansible-core >= 2.16, < 2.22` (the CI range); no extra
Ansible collections are needed. The target needs internet access to download
packages, binaries, and container images.

From the repository root:

```bash
python3 -m pip install 'ansible-core>=2.16,<2.22'
cp ansible/inventory.example.yml ansible/inventory.yml
# Edit the host, SSH user, domains, email, and bind address in inventory.yml.
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --ask-become-pass
```

Omit `--ask-become-pass` if using passwordless sudo. For a public deployment,
configure platform and wildcard application DNS and the host/provider firewall
before running the playbook. Allow TCP 80/443 and restrict SSH to
administrators; account for Docker's published ports. See the root README for
host capacity and network requirements. The playbook does not change the
firewall.

The playbook installs Docker from its official APT repository, verifies
downloaded kubectl and k3d checksums, copies deployment sources to
`/opt/developer-platform`, generates secrets on the target, prepares the bounded
Tempo filesystem, and invokes `scripts/operations/deploy-platform.py`. That
shared command performs the deployment checks and controlled stop/remove
sequence, calls `scripts/up.sh`, and waits for API readiness. Local operators
can invoke the same deployment command on a prepared host. See the
[shared configuration and deployment guide](../../docs/operators/configuration-and-deployment.md).
The Tempo script is transferred with the new source, so it does not need to
exist on the host before deployment. The playbook then waits for the API
dependency-readiness endpoint. Bootstrap also waits for Alloy's internal
readiness health check; a restarting/unhealthy collector fails deployment rather
than being masked by API/Prometheus readiness. This does not attest log
ingestion or seven-day retention. The controller's `.env` and `.runtime` are not
transferred. Each successful deployment writes
`.runtime/installation-record.json` (root-only, no secrets) with the source
revision (`+dirty` if the controller checkout has uncommitted changes), host OS,
Docker/Compose/k3d/kubectl versions, running Compose image references with IDs,
and the non-secret deployment parameters. The installation and runtime
directories are root-only; `.env` has mode 0600. Run manual maintenance commands
with sudo from the installation directory. kubectl is also installed at
`/usr/local/bin/kubectl` for host administration. For example, run

```bash
sudo kubectl --kubeconfig /opt/developer-platform/.runtime/admin.kubeconfig \
  get nodes
```

## Reapplying an installation

Rerunning the playbook reapplies sources and endpoints and reconciles the
running platform. Endpoint/policy defaults come from `.env.example`; the Ansible
filter plugin and local configuration command use the same validators and Tempo
renderer. Ansible passes non-secret settings to the configuration command on
stdin and preserves the existing inventory interface. It writes the selected
`platform_trace_sample_rate` to `PLATFORM_TRACE_SAMPLE_RATE`, defaulting to
`1.0` even when a previous `.env` selected 10% sampling. Existing
tracing-enabled application declarations must be reapplied so their sampler
environment changes too; an API restart alone cannot change a running
application's sampler. An already installed `/usr/local/sbin/platform-backup` is
refreshed from the matching transferred source before the API starts. Its
configuration, credentials, schedule and verified history are retained; this
does not install or enable a new backup service. Fresh backup setup still uses
the operations playbook. After validating the transferred Compose configuration
and confirming that no backup or availability drill is active, deployment
performs a controlled full outage of the Compose services. It stops and removes
their containers, but preserves named volumes, `.env`, the k3d cluster, and the
shared Docker network. PostgreSQL starts and becomes healthy first. Bootstrap
then starts Keycloak and the Platform API (and their identity initializers)
before recreating the remaining dynamically addressed services, so monitoring
and edge containers cannot claim their fixed addresses. Address settings are
validated before the outage, and bootstrap checks live ownership before starting
services and after starting k3d. An unexpected owner is reported without secrets
and is never disconnected automatically. This is intentionally not
`docker compose down`: k3d remains attached to the shared network, so that
network must not be removed. The external watchdog can alert if the deployment
exceeds its heartbeat window.

k3d installation and bootstrap run on every deployment and report changes, even
if configuration is unchanged. Bootstrap refreshes the k3d load balancer when
the Kubernetes API is stale after a Docker restart. Source extraction does not
delete obsolete remote files. Backups and the external watchdog require the
separate [operations](../../docs/operators/backup-and-recovery.md) and
[watchdog](../../operations/watchdog/README.md) setup.

```bash
ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

`--check` only previews host package/directory changes; source transfer,
generated configuration, and bootstrap are skipped. It is not a deployment
validation on a fresh host. After deployment, the optional
`scripts/tests/platform/smoke.py` test creates and retains a project; it is not
run
automatically.

For a fresh-install sequence covering basic users, revocable CI credentials, and
platform tests, use
[Fresh deployment and basic platform tests](../../docs/operators/validation/acceptance.md).
Backup, watchdog/heartbeat, and Alertmanager setup and drills remain separate
operational tracks with their own inventories and protected credentials.

Installation references:
[Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) and
[kubectl on Linux](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/).

See [watchdog deployment](../../operations/watchdog/ansible/README.md) and
[heartbeat deployment](../../operations/heartbeat/README.md).

## Backups

See [backup setup and scheduling](../../operations/backup/README.md).

## Alertmanager email

See
[inventory-based SMTP setup and delivery checks](../../operations/alertmanager/README.md).
