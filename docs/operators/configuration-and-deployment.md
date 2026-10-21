# Shared configuration and deployment

Local setup and Ansible use the same configuration validators and controlled
deployment command. Ansible owns Ubuntu package installation, Docker/systemd
setup, source transfer, privileged file ownership, backup-runner installation,
and installation records. Those host-management steps remain Ansible tasks.

## Configure the platform

`python3 scripts/init.py` generates missing credentials without replacing
existing ones. Both paths then use `scripts/setup/configure-platform.py` to
validate settings and apply optional non-secret configuration. Host scripts use
only the Python standard library; the Ansible filter plugin adapts the same
validation module on the controller.

Defaults for endpoints and platform policy come from `.env.example`. Store and
network options use the same types and restrictions as the
[Ansible inventory options](../../ansible/docs/inventory-options.md). The shared
Tempo renderer changes only its retention field and preserves other settings and
comments.

For local configuration, initialize the checkout, edit `.env`, and validate:

```bash
python3 scripts/init.py
# Edit .env for domains, stores, networks, capacity, and tracing.
python3 scripts/setup/configure-platform.py --check
python3 scripts/setup/configure-platform.py
```

`.env` is the local configuration file. Use `.env.example` as the reference for
available settings. When selecting optional stores with `COMPOSE_PROFILES`, add
capacity budgets for those providers in `STORE_CAPACITY_BYTES`. When changing a
subnet, update its fixed service addresses consistently before first startup.
Existing networks require a separately planned migration.

The configuration command validates `.env` and synchronizes Tempo retention if
`PLATFORM_TRACE_RETENTION` is set there, for example `168h`. Otherwise the
current Tempo retention is retained. `--check` performs no writes. `--runtime`
also honors environment overrides, matching Compose and bootstrap helpers.
Startup and deployment invoke this validation automatically. Configuration is
validated before any writes, and `.env` permissions are enforced as `0600`
without replacing existing secrets.

Remote configuration belongs in Ansible inventory. The `--stdin` interface is
used by Ansible to pass rendered settings; local setup does not need another
configuration file.

Ansible passes its rendered settings to this command through stdin with
`no_log`, after controller-side validation. Existing inventory names and
optional group semantics remain supported. As before, omitted core inventory
settings use deployment defaults, while omitted optional groups retain remote
values. Ansible manages tracing with the selected inventory defaults on every
deployment.

## Start services or perform a controlled deployment

Routine local startup remains:

```bash
bash scripts/up.sh
```

It validates shared configuration and runs the existing bootstrap. It does not
perform the deployment command's full stop/remove sequence. Complete the
[local prerequisites and identity bootstrap](install-local.md) first.

For an existing installation, local operators and Ansible can use the same
explicit deployment command:

```bash
python3 scripts/operations/deploy-platform.py --check
python3 scripts/operations/deploy-platform.py --readiness-timeout 300
```

Run this on the platform host, from the checkout or using an absolute script
path. Use a privileged shell for the root-owned remote installation. This
command does not install host dependencies, generate missing secrets, or prepare
the Tempo filesystem; complete host preparation first.

The shared sequence:

1. Validate configuration, Compose, existing network subnets, the Tempo mount,
   and required tools. On systemd hosts, refuse active backup/availability jobs;
   failure to inspect systemd also stops deployment. Hosts without systemd skip
   that service check.
1. Apply shared configuration and prepare selected store
   credentials/configuration before any service outage.
1. Stop Compose services with a 60-second timeout, then remove stopped
   containers.
1. Run `scripts/up.sh` to reconcile the platform and workload cluster.
1. Wait for the API dependency-readiness endpoint within the selected budget.

The deployment interrupts Compose services. It retains named volumes and the k3d
cluster/network; it never runs `docker compose down`. `--check` stops after
read-only prerequisites and does not generate store configuration or stop
services. It validates an already prepared host, rather than simulating a fresh
installation. A preflight failure leaves services running; a failure after the
stop phase can leave a partially started installation that needs investigation.

Ansible runs the same preflight before refreshing an already installed backup
runner, then invokes the full deployment command under its bootstrap timeout.
Its host/source preparation and installation record remain remote orchestration.

## Offline verification

From the repository root with development requirements installed:

```bash
python3 -m unittest discover -s scripts/tests/unit -v
python3 -m unittest discover -s ansible/tests/unit -v
ansible-playbook -i ansible/inventory.example.yml \
  ansible/deploy.yml --syntax-check
```

These tests verify local/inventory configuration parity, secret preservation,
validation before writes, deployment ordering, maintenance refusal, and the
non-mutating check mode. They do not deploy a platform.
