# Remote installation with Ansible

Status: current supported deployment path. Last reviewed October 9, 2026.

Use the repository's [Ansible deployment](../../ansible/README.md) for an
existing Ubuntu host. The playbook prepares and updates the platform in
`/opt/developer-platform`; its configuration and runtime directories are
root-only.

Before deploying, define the inventory host and SSH user, platform, application,
and identity domains, TLS email address, edge bind address, and protected
variables. Point the platform, identity, and wildcard application DNS names to
the host. Permit public TCP 80/443 and limit SSH to the administration network.
Check the Docker and k3d subnets for conflicts before first deployment.

Review the [inventory example](../../ansible/inventory.example.yml) before using
it on an existing installation. Configure the optional `platform_stores` group
with a provider list and positive per-provider capacity budgets. Network groups
select a subnet and derive all fixed addresses, with optional service overrides;
choose them before first startup. The playbook refuses existing network subnet
changes before stopping services. Omitted optional groups preserve remote
settings; explicit defaults in a copied example take ownership of those
settings.

The inventory also supports initial administrator subject, Kubernetes image pin,
build/start and readiness timeouts, and consistent advertised/bastion SSH
settings. The bastion itself remains a separate opt-in installation. See the
[option reference](../../ansible/docs/inventory-options.md#additional-deployment-options)
and the [data-store workflow](data-stores.md#selecting-shared-services).
Dashboards are provisioned automatically. `platform_trace_sample_rate: 1.0` and
`platform_trace_retention: 24h` expose the chosen defaults; deployment applies
them to the API/application sampler configuration and Tempo respectively.
Reapply existing tracing-enabled application declarations after changing
sampling.

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml
```

Ansible uses the
[shared configuration and deployment commands](configuration-and-deployment.md)
for settings validation, store/network selection, tracing, and controlled
service reconciliation. Host provisioning and source transfer remain Ansible
responsibilities.

After deployment:

1. Complete [identity bootstrap](identity-and-access.md).
1. Verify API, database, cluster, edge route, and a representative application.
1. Configure [monitoring](monitoring.md) and actual alert delivery.
1. Configure [encrypted off-host backups](backup-and-recovery.md).
1. Deploy the [heartbeat](components/heartbeat.md) and, on an independent host,
   the [watchdog](components/watchdog.md).
1. Record the repository revision, image versions, inventory, test results, and
   remaining environment limitations.

Caddy obtains platform certificates automatically. Workload on-demand TLS is
authorized only for provisioned project hosts. Keep Prometheus and Grafana bound
to loopback and use an SSH tunnel unless an explicit protected access design
says otherwise.

The source-adjacent Ansible README remains the detailed variable, playbook,
drill, and rollback reference. This page is the canonical deployment sequence.
