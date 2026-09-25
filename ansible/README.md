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
Back up `.env`, especially `DATABASE_KEY`, as described in [operations](../docs/operations.md).

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
[operations](../docs/operations.md) and [watchdog](../watchdog/README.md) setup.

```bash
ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

`--check` only previews host package/directory changes; source transfer, generated
configuration, and bootstrap are skipped. It is not a deployment validation on a
fresh host. After deployment, the optional `scripts/smoke.py` test creates and
retains a project; it is not run automatically.

Installation references: [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
and [kubectl on Linux](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/).

## External watchdog via SCP

Use `deploy-watchdog.yml` for an existing PHP/MySQL hosting account with SSH shell
access and SCP support. Ansible runs entirely on `localhost`, invoking local
OpenSSH `ssh` and `scp` commands through `sshpass`; the remote host does not need
Python or Ansible. Install `sshpass` on the controller (for example,
`sudo apt-get install sshpass` on Ubuntu/Debian).
SCP uses `-O` to select the SCP protocol on OpenSSH 9+. No sudo is required.
The playbook prompts privately for the SSH password. For automation, supply
`watchdog_ssh_password` using an Ansible Vault encrypted variables file with
`-e @secrets.yml --ask-vault-pass`. The password is passed to `sshpass` through
the environment, and remote command output is hidden to prevent secret logging.
Verify and accept the server's SSH host key before deployment, for example using
`ssh -p 22 hosting-user@status.example.com`; host key checking remains enabled.
SSH aliases and connection settings in `~/.ssh/config` are supported.

```bash
cp watchdog/config.example.php watchdog/config.local.php
# Edit database credentials, token, and email settings; never use example secrets.
chmod 600 watchdog/config.local.php
cp ansible/inventory.watchdog.example.yml /tmp/watchdog-inventory.yml
# Edit the host, SSH user, private installation directory, and optional cron settings.
ansible-playbook -i /tmp/watchdog-inventory.yml ansible/deploy-watchdog.yml
```

Set the site's DocumentRoot exclusively to `<watchdog_install_dir>/public` before
deployment. The parent directory must not be served by another website. PHP must
run as the deployment user to read the private configuration (mode 0600).
The playbook uploads an explicit list of application files; it does not copy local
secrets unless `watchdog_config_file` is supplied. That variable names a local
configuration file (use an absolute path for custom locations). Omit it after the
first deployment to preserve the remote configuration; when supplied, it replaces
the remote configuration. An existing configuration is required if it is omitted.

Create the MySQL database/user using the hosting provider's tools, then run
`php /absolute/path/watchdog/import-schema.php` on the hosting server. The playbook
uploads the importer and schema but does not run the import automatically. Configure HTTPS, mail delivery, and PHP extensions as
described in the [watchdog setup](../watchdog/README.md). These steps and the
platform heartbeat sender are not provisioned by this upload playbook.
Set `watchdog_manage_cron: true` to install the every-minute job in the SSH user's
crontab; otherwise configure it through the hosting provider. Setting it to false
leaves any existing job untouched. `watchdog_php_binary` defaults to `/usr/bin/php`.
`watchdog_source_dir` defaults to this checkout's `watchdog` directory.

Reruns upload all release files without deleting other remote files and report
changes on every upload. `--check` validates local inputs only and skips all SSH
and SCP commands. It does not validate the remote installation. Syntax validation:

```bash
ansible-playbook -i ansible/inventory.watchdog.example.yml ansible/deploy-watchdog.yml --syntax-check
```

## Platform heartbeat

`deploy-heartbeat.yml` runs on localhost and delegates installation to the platform
host named by `heartbeat_target` (default `platform`). The target needs Ubuntu
22.04+ or Debian with systemd, Python 3, SSH access, and sudo privileges. The
platform API and Prometheus must already be available on local ports 8000 and
9090. The playbook installs Python and CA certificates, the heartbeat script,
a private environment file, and the systemd service and timer.

```bash
cp ansible/inventory.heartbeat.example.yml /tmp/heartbeat-inventory.yml
# Edit the platform SSH host/user and heartbeat_url.
ansible-playbook -i /tmp/heartbeat-inventory.yml ansible/deploy-heartbeat.yml --ask-pass --ask-become-pass
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
ansible-playbook -i ansible/inventory.heartbeat.example.yml ansible/deploy-heartbeat.yml --syntax-check
```
