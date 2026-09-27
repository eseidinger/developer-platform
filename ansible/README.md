# Ansible deployment

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
API health endpoint. The controller's `.env` and `.runtime` are not transferred.
The installation and runtime directories are root-only; `.env` has mode 0600.
Run manual maintenance commands with sudo from the installation directory.
kubectl is also installed at `/usr/local/bin/kubectl` for host administration.
For example, run `sudo kubectl --kubeconfig /opt/developer-platform/.runtime/admin.kubeconfig get nodes`.

Existing `.env` secrets, volumes, and project state are preserved. Inventory values
manage only `PLATFORM_DOMAIN`, `APPS_DOMAIN`, `TLS_EMAIL`, and `EDGE_BIND_IP`.
Other settings retain their generated or existing values. For a custom subnet or
K3S image, prepare the target `.env` using `scripts/init.py` and edit it before the
first deployment. Existing clusters are not automatically upgraded by bootstrap.
Back up `.env`, especially `DATABASE_KEY`, as described in [operations](../docs/05-operations/backup-recovery.md).

Useful inventory overrides:

| Variable | Default | Purpose |
| --- | --- | --- |
| `platform_install_dir` | `/opt/developer-platform` | Absolute target directory |
| `platform_source_dir` | Repository containing the playbook | Local checkout to deploy |
| `platform_install_docker` | `true` | Set `false` to use an existing compatible Docker installation |
| `platform_kubectl_version` | `v1.36.4` | kubectl release compatible with the default Kubernetes 1.36 cluster |
| `platform_domain` | `platform.localhost` | Platform API domain |
| `platform_apps_domain` | `apps.localhost` | Application domain suffix |
| `platform_tls_email` | `admin@example.com` | ACME contact email |
| `platform_edge_bind_ip` | `127.0.0.1` | Use `0.0.0.0` for public ingress |

For an existing host with Docker, prefer `platform_install_docker: false` to
avoid changing its package source. Conflicting distribution Docker packages are
not automatically removed. The existing engine must provide Compose >= 2.20.3.

Rerunning the playbook reapplies sources and endpoints and reconciles the running
platform. k3d installation and bootstrap run on every deployment and report
changes, even if configuration is unchanged. Source extraction does not delete
obsolete remote files. Backups and the external watchdog require the separate
[operations](../docs/05-operations/backup-recovery.md) and [watchdog](../operations/watchdog/README.md) setup.

```bash
ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

`--check` only previews host package/directory changes; source transfer, generated
configuration, and bootstrap are skipped. It is not a deployment validation on a
fresh host. After deployment, the optional `scripts/smoke.py` test creates and
retains a project; it is not run automatically.

Installation references: [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
and [kubectl on Linux](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/).

See [watchdog deployment](../operations/watchdog/ansible/README.md) and [heartbeat deployment](../operations/heartbeat/README.md).

## Backups

See [backup setup and scheduling](../operations/backup/README.md).

## Alertmanager email

See [inventory-based SMTP setup and delivery checks](../operations/alertmanager/README.md).
