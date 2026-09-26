# Platform heartbeat

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
