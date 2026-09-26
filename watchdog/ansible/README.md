# Watchdog and heartbeat deployment

Run these commands from the repository root.

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
cp watchdog/src/config.example.php watchdog/src/config.local.php
# Edit database credentials, token, and email settings; never use example secrets.
chmod 600 watchdog/src/config.local.php
cp watchdog/ansible/inventory.watchdog.example.yml /tmp/watchdog-inventory.yml
# Edit the host, SSH user, private installation directory, and optional cron settings.
ansible-playbook -i /tmp/watchdog-inventory.yml watchdog/ansible/deploy-watchdog.yml
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
described in the [watchdog setup](../README.md). These steps and the
platform heartbeat sender are not provisioned by this upload playbook.
Set `watchdog_manage_cron: true` to install the every-minute job in the SSH user's
crontab; otherwise configure it through the hosting provider. Setting it to false
leaves any existing job untouched. `watchdog_php_binary` defaults to `/usr/bin/php`.
`watchdog_source_dir` defaults to this checkout's `watchdog/src` directory.

Reruns upload all release files without deleting other remote files and report
changes on every upload. `--check` validates local inputs only and skips all SSH
and SCP commands. It does not validate the remote installation. Syntax validation:

```bash
ansible-playbook -i watchdog/ansible/inventory.watchdog.example.yml watchdog/ansible/deploy-watchdog.yml --syntax-check
```

## Platform heartbeat

`deploy-heartbeat.yml` runs on localhost and delegates installation to the platform
host named by `heartbeat_target` (default `platform`). The target needs Ubuntu
22.04+ or Debian with systemd, Python 3, SSH access, and sudo privileges. The
platform API and Prometheus must already be available on local ports 8000 and
9090. The playbook installs Python and CA certificates, the heartbeat script,
a private environment file, and the systemd service and timer.

```bash
cp watchdog/ansible/inventory.heartbeat.example.yml /tmp/heartbeat-inventory.yml
# Edit the platform SSH host/user and heartbeat_url.
ansible-playbook -i /tmp/heartbeat-inventory.yml watchdog/ansible/deploy-heartbeat.yml --ask-pass --ask-become-pass
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
ansible-playbook -i watchdog/ansible/inventory.heartbeat.example.yml watchdog/ansible/deploy-heartbeat.yml --syntax-check
```

## Upgrade for backup signals

The release list includes `backup.php` and `public/backup.php`. After uploading,
re-run `php /absolute/path/watchdog/import-schema.php` on the hosting account to
add the independent backup table. Existing monitor/history rows are preserved.
Then add a new `backup_token` to the private configuration, distinct from `token`;
keep existing mail/heartbeat settings. You can edit the remote configuration or
explicitly supply a complete local configuration using `watchdog_config_file`.
The latter replaces the remote file, so preserve all existing settings.

Enabling backup monitoring can send a BACKUP DOWN/no-backup alert on the next cron
run until the first verified backup arrives. It does not change host heartbeat
status. Configure and deploy [scheduled platform backups](../../ansible/README.md#scheduled-backups-and-independent-backup-alerts)
after the authenticated backup endpoint is available. Upload/syntax success does
not establish database migration, cron execution or real email delivery.
