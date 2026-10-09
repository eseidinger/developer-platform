# Remote installation with Ansible

Status: current supported deployment path. Last reviewed October 9, 2026.

Use the repository's [Ansible deployment](../../ansible/README.md) for an existing
Ubuntu host. The playbook prepares and updates the platform in
`/opt/developer-platform`; its configuration and runtime directories are
root-only.

Before deploying, define the inventory host and SSH user, platform, application,
and identity domains, TLS email address, edge bind address, and protected
variables. Point the platform, identity, and wildcard application DNS names to the
host. Permit public TCP 80/443 and limit SSH to the administration network. Check
the Docker and k3d subnets for conflicts before first deployment.

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml
```

After deployment:

1. Complete [identity bootstrap](identity-and-access.md).
2. Verify API, database, cluster, edge route, and a representative application.
3. Configure [monitoring](monitoring.md) and actual alert delivery.
4. Configure [encrypted off-host backups](backup-and-recovery.md).
5. Deploy the [heartbeat](components/heartbeat.md) and, on an independent host,
   the [watchdog](components/watchdog.md).
6. Record the repository revision, image versions, inventory, test results, and
   remaining environment limitations.

Caddy obtains platform certificates automatically. Workload on-demand TLS is
authorized only for provisioned project hosts. Keep Prometheus and Grafana bound
to loopback and use an SSH tunnel unless an explicit protected access design says
otherwise.

The source-adjacent Ansible README remains the detailed variable, playbook, drill,
and rollback reference. This page is the canonical deployment sequence.
