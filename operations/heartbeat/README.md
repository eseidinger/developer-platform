# Platform heartbeat

Use the canonical [heartbeat overview](../../docs/operators/components/heartbeat.md)
for its place in the operating model. This page retains deployment and drill
details close to the component source.

Run deployment commands from the repository root.

## Platform heartbeat

`deploy-heartbeat.yml` runs on localhost and delegates installation to the platform
host named by `heartbeat_target` (default `platform`). The target needs Ubuntu
22.04+ or Debian with systemd, Python 3, SSH access, and sudo privileges. The
platform API and Prometheus must already be available on local ports 8000 and
9090. The playbook installs Python and CA certificates, the heartbeat script,
a private environment file, and the systemd service and timer.

```bash
cp operations/heartbeat/ansible/inventory.heartbeat.example.yml /tmp/heartbeat-inventory.yml
# Edit the platform SSH host/user and heartbeat_url.
ansible-playbook -i /tmp/heartbeat-inventory.yml operations/heartbeat/ansible/deploy-heartbeat.yml --ask-pass --ask-become-pass
```

Enter the same token configured in the external watchdog's `config.local.php` at
the private token prompt. Tokens must contain at least 32 letters, digits,
underscores, or hyphens. For automation, supply `heartbeat_token` using an Ansible
Vault encrypted variables file (`-e @secrets.yml --ask-vault-pass`). Use the normal
Ansible `ansible_password` and `ansible_become_password` Vault variables for SSH
and sudo passwords. Omit the corresponding password flags when using SSH keys
or passwordless sudo. Ansible versions that require `sshpass` for password
connections need it installed on the controller. Verify the SSH host key first.

The script is installed at `/usr/local/lib/developer-platform/heartbeat.py`, so
the systemd dynamic user can read it even when `/opt/developer-platform` is
root-only. The root-owned `/etc/developer-platform/watchdog.env` has mode 0600;
systemd loads it before dropping privileges. Existing endpoint/token settings
are replaced by the supplied values on each deployment. They are excluded from
Ansible logs and diffs.

The timer sends a heartbeat about once per minute, only after both the platform
API readiness and Prometheus readiness checks pass. It starts automatically at
boot, with an initial two-minute delay and up to five seconds of jitter. This
playbook enables the timer; it does not validate delivery to the live watchdog.
On the platform host, inspect it with:

```bash
sudo systemctl status platform-heartbeat.timer
sudo journalctl -u platform-heartbeat.service -n 30
```

`--check` previews remote file/package changes but skips timer activation. Syntax
validation does not connect to the host:

```bash
ansible-playbook -i operations/heartbeat/ansible/inventory.heartbeat.example.yml operations/heartbeat/ansible/deploy-heartbeat.yml --syntax-check
```

## Availability drills

The following playbooks exercise the existing lab and automatically restore the
chosen failure boundary. Run them from the controller, one at a time. They write
private reports under `/var/lib/developer-platform-availability-drill/` on the
platform host and fetch a copy into `.runtime/availability-drill/` on the
controller.

Cluster mode stops only the k3d server container. It waits for Prometheus to see
the `kubernetes-state` target down and for `ScrapeTargetDown` to fire, then
starts the same container and verifies all three nodes, the scrape target, and
alert resolution:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.yml \
  operations/heartbeat/ansible/drill-cluster-availability.yml
```

Confirm the `ScrapeTargetDown` FIRING and RESOLVED emails. The normal default
wait adds 90 seconds after the alert begins firing so Alertmanager can notify.
No project data, volumes, namespaces, or container definitions are removed.

Docker mode is a local host-boundary simulation: it stops Docker for six minutes
so the existing heartbeat becomes overdue at the external watchdog, then starts
Docker. Recovery then performs the same controlled Compose reconciliation as a
deployment: Compose containers are stopped and removed without deleting volumes,
PostgreSQL starts first, and the remaining services and existing k3d cluster are
reconciled. The drill requires PostgreSQL, the Platform API, Prometheus,
Kubernetes nodes, and the heartbeat timer to recover before it can pass:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.yml \
  operations/heartbeat/ansible/drill-docker-availability.yml
```

Confirm the external watchdog DOWN and UP emails. This is not a physical host
or power-loss test: it cannot independently recover a machine that is actually
offline. Recovery invokes the normal bootstrap reconciliation, but does not
delete or recreate the existing cluster, named volumes, or project data.

Both drills are live changes. Do not run them during provisioning, a backup
capture, or another availability exercise. If a run fails, use the fetched report
and `journalctl -u <printed-unit> --no-pager`, then verify `docker compose ps`,
`kubectl --kubeconfig /opt/developer-platform/.runtime/admin.kubeconfig get nodes`,
and the heartbeat timer before retrying. A report proves observed monitoring and
recovery state; email receipt remains an operator confirmation.
