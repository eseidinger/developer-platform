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
[operations](../docs/05-operations/backup-recovery.md) and [watchdog](../watchdog/README.md) setup.

```bash
ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

`--check` only previews host package/directory changes; source transfer, generated
configuration, and bootstrap are skipped. It is not a deployment validation on a
fresh host. After deployment, the optional `scripts/smoke.py` test creates and
retains a project; it is not run automatically.

Installation references: [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
and [kubectl on Linux](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/).

Watchdog and heartbeat deployment instructions are in [watchdog/ansible](../watchdog/ansible/README.md).

## Encrypted S3 backup repository setup

[setup-backup.yml](setup-backup.yml) installs the distribution's `restic` package
and CA certificates on the existing Ubuntu platform host. It configures a
root-only restic command and verifies access to an encrypted S3 repository.
It runs independently of `deploy.yml` and does not redeploy or stop the platform.
The controller needs the same Ansible prerequisites described above.

The example uses the confirmed Hetzner destination:
`s3:https://hel1.your-objectstorage.com/eseidinger/developer-platform`, region
`hel1`. The bucket must already exist and the prefix must be reserved for this
repository. Review the destination before initialization; an S3 prefix is not an
access-control boundary. Use credentials with the necessary repository access.

From the local checkout on your Ansible controller:

```bash
cp ansible/inventory.backup.example.yml ansible/inventory.backup.yml
# Set ansible_host and ansible_user for node-01.
ansible-playbook -i ansible/inventory.backup.yml ansible/setup-backup.yml \
  -e backup_restic_initialize=true
```

This first-run command explicitly allows repository creation. The playbook first
tries to open the repository; if successful, initialization is skipped. If opening
fails, initialization is attempted only with this flag, and restic refuses an
existing repository config. Authentication/network/password failures remain
failures; no existing repository is removed or reset. For an existing repository,
omit the flag. Reruns preserve its encryption password and fail if a different
password is supplied; they may update the S3 credentials.

The playbook prompts privately for the access key ID, secret key and repository
password (at least 20 characters, entered twice). Generate and save the repository
password in a password manager independently of the platform host **before** the
first run. Store recovery access to the S3 credentials there too. The repository
password is distinct from the S3 secret key. Changing the local password does not
rotate a restic repository key; use restic's separate key-management workflow.

If SSH uses a password, add `--ask-pass`; for a non-root sudo account, add
`--ask-become-pass` when needed. For unattended runs, use an encrypted vars file:

```bash
ansible-vault create ansible/backup-secrets.yml
# In the editor, define backup_s3_access_key, backup_s3_secret_key,
# and backup_restic_password. This path is ignored by Git.
ansible-playbook -i ansible/inventory.backup.yml ansible/setup-backup.yml \
  -e @ansible/backup-secrets.yml --ask-vault-pass
```

Use the initialization flag as well if this is the first run. Do not pass secret
values inline on the command line. Secret tasks suppress output and diffs.

Files installed on the host:

| Path | Purpose / permissions |
|---|---|
| `/etc/developer-platform/backup/` | Root-only configuration directory, `0700` |
| `restic.env` inside that directory | Shell-quoted S3 configuration/credentials, `0600` |
| `restic-password` inside that directory | Repository password, `0600`; preserved on reruns |
| `/usr/local/sbin/platform-restic` | Root-only configured command, `0700` |

On the host, inspect the repository without printing credentials:

```bash
sudo /usr/local/sbin/platform-restic snapshots
```

An empty snapshot list is expected for a new repository. Successful setup proves
repository creation/opening and snapshot listing, **not backup or recovery**.
The wrapper loads trusted root-owned shell configuration; it is not a systemd
EnvironmentFile. Arguments are forwarded unchanged to restic.

The confirmed policy remains every 12 hours, retaining 14 daily, 8 weekly and
6 monthly recovery points, with RPO 24 hours and RTO four hours. This setup
playbook does **not** schedule capture, apply retention/prune, or perform a backup
or restore. Use [scheduled backup deployment](#scheduled-backups-and-independent-backup-alerts) for capture, retention and independent reporting. Live verification and restore remain OPS-006-T02/T03 work in the
[delivery backlog](../docs/04-development/delivery-backlog.md). Preserve platform
configuration, database roles/data, secrets and required service state in the
future recovery bundle; a repository alone does not cover that inventory.

Validate without deploying:

```bash
ansible-playbook -i ansible/inventory.backup.example.yml ansible/setup-backup.yml --syntax-check
```

`--check` connects to inspect the host and previews package/file changes, but skips
all restic commands and repository creation/access checks. It still requires the
private input variables and validates an existing password if present. A successful
check run does not verify S3 permissions or password recovery.

References: [restic S3 repositories](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#s3-compatible-storage)
and [restic installation](https://restic.readthedocs.io/en/stable/020_installation.html).

## Scheduled backups and independent backup alerts

After repository setup, [deploy-backup.yml](deploy-backup.yml) installs the backup
runner and systemd units. The existing platform stays deployed. **Each backup
briefly stops Caddy and Grafana while archiving their named volumes**, then starts
the same containers before S3 upload. Public ingress and Grafana are interrupted
during that capture window; PostgreSQL and workloads keep running. Avoid concurrent
platform deployment, manual container replacement or configuration changes during
backup capture. Measure this window on the first run.

Deploy in this order:

1. Update the external watchdog using its existing [deployment playbook](../watchdog/ansible/README.md).
   Re-run `php /absolute/path/watchdog/import-schema.php` on the hosting account
   to add `backup_monitor`; repeat import preserves existing heartbeat/history.
2. Add a **new**, random `backup_token` of at least 32 letters/digits/underscores/hyphens
   to the hosting account's private `config.local.php`. It must differ from the
   host heartbeat token. Keep existing database/mail/heartbeat settings. The token
   is also supplied privately to `deploy-backup.yml`. Enabling it starts backup
   monitoring: a BACKUP DOWN/no-backup email is expected until the first verified
   backup is reported. Existing host outage emails continue independently.
3. Set `backup_watchdog_url` in `ansible/inventory.backup.yml` to the new endpoint,
   for example `https://status.example.com/backup.php`, and keep `backup_instance`
   stable (`node-01`). This identity scopes retention; changing it creates a new
   retention group. The endpoint's authenticated preflight must pass before the
   playbook enables any timer.
4. Deploy and request the first backup from the controller:

```bash
ansible-playbook -i ansible/inventory.backup.yml ansible/deploy-backup.yml \
  -e backup_run_now=true
```

Enter the new backup token at the private prompt. Add `--ask-pass` / `--ask-become-pass`
if your SSH/sudo setup needs them. For unattended use, store `backup_watchdog_token`
in the same Vault-encrypted variables file used by setup and pass
`-e @ansible/backup-secrets.yml --ask-vault-pass`. The deployment does not need the
S3 keys or restic password again: it uses the existing root-only configuration.
No email destination is changed by this playbook. Backup alerts use the existing
external watchdog mail transport and recipients.

The first backup starts asynchronously; a successful Ansible run does not mean the
backup finished. On `node-01`:

```bash
sudo systemctl status platform-backup.service --no-pager
sudo journalctl -u platform-backup.service -n 40 --no-pager
sudo cat /var/lib/developer-platform-backup/status.json
sudo /usr/local/sbin/platform-restic snapshots --tag developer-platform,verified
sudo systemctl list-timers platform-backup.timer platform-backup-notify.timer
```

Expected after completion: `result: success`, a `last_verified_snapshot`, a recent
`last_verified_capture`, and the verified snapshot listed remotely. Confirm the
external **BACKUP UP** email after the initial DOWN notification. The ordinary host
heartbeat cannot refresh this state. Service exit failure can also mean a valid
backup has a pending notification; distinguish `status.json` from
`notification.json` and inspect the retry service.

### Capture, verification and retention

The timer runs at **00:00 and 12:00 UTC**, with persistent catch-up after downtime.
The service limits a complete run to two hours. A process lock excludes overlapping
captures, retention and notification updates. A boot recovery unit and
`ExecStopPost` restart the exact containers recorded before an interruption and
mark unfinished attempts failed. Do not manually replace these containers while
recovery intent exists. Restart failures retain `resume.json` for investigation.

Each encrypted recovery bundle contains:

- A compressed `pg_dumpall` of databases, roles and the platform catalog. This is
  not a single transaction across databases; coordinate writes if cross-database
  consistency is required.
- Deployed source/configuration (`compose.yaml`, `.env`, `scripts`, `platform`,
  `infrastructure`, `persistence`), including `DATABASE_KEY` and database credentials.
- `/etc/developer-platform`, including backup/heartbeat credentials; installed
  backup helper programs and systemd units. Keep independent copies of recovery
  credentials outside this host and repository so they are available to decrypt it.
- Stopped-service archives of Caddy data/config and Grafana state, including SQLite.
- A manifest with capture start time, checksums, run identity and installation
  identity, plus installed restic/PostgreSQL versions, container image IDs/digests
  and optional `backup_source_revision` from inventory. Source files are included
  even if the remote deployment is not a Git checkout.

The runner uploads with a `pending` tag, restores that **exact snapshot** into a
private temporary directory and compares all bundle checksums. Only then is it
retagged `verified`, and its resulting full snapshot ID recorded. Failed readback
snapshots remain pending for diagnosis and cannot displace verified recovery
points through retention. Temporary plaintext staging/readback is removed after
the run or interrupted-run recovery. Allow disk capacity for both copies.

Retention selects only this installation's `developer-platform,verified` snapshots,
keeping 14 daily, 8 weekly, 6 monthly and at least the latest snapshot. These rules
overlap rather than guaranteeing 28 distinct snapshots. `forget --prune` reclaims
unreferenced data; `restic check` then checks repository structure. Retention runs
only after successful readback. A retention failure reports failure while preserving
the recorded verified snapshot. Pending snapshots require explicit investigation
and separate cleanup, and are not automatically removed.

Excluded: raw PostgreSQL volumes, Kubernetes node files, generated cluster
credentials (regenerate on bootstrap), telemetry history volumes (Prometheus/Loki/
Alertmanager), and the independently hosted watchdog database/configuration.
Back up the external watchdog through its hosting provider separately. Images are
recorded, not exported: ensure required images remain available or reproducible.

### Failure signals and remaining acceptance

The runner posts start/success/failure with a unique run ID and capture-start time
using a separate backup token. An external cron checks backup age even if the
platform host or Prometheus is down. It alerts for a failed attempt, no verified
backup, a running attempt older than two hours, or capture age over 24 hours.
Stale events cannot override newer results; failure does not refresh the last
successful capture. Notifications are deduplicated and failed mail handoff is
retried by cron. Host and backup channels share the external hosting/mail provider;
independent watchdog-hosting failure detection remains separate work.

Notification transport failure does not invalidate a verified snapshot. A durable
outbox retries every five minutes. If initial start delivery fails, a later success
or failure carries the complete run identity; the external monitor can still
accept it without a start event. Meanwhile, its previous success continues aging.

This implements automation; **SQL/application recovery, measured RPO/RTO, live S3
failure tests and actual backup-alert receipt still need operational evidence**.
Exact-file readback is not an application restore exercise. Continue with
[backup and recovery](../docs/05-operations/backup-recovery.md).

Local validation:

```bash
ansible-playbook -i ansible/inventory.backup.example.yml ansible/deploy-backup.yml --syntax-check
python3 -m unittest discover -s tests -v
php watchdog/tests/backup.php
```

`--check` previews host installation without contacting the backup endpoint or
repository, enabling timers, or executing backups. It still requires configured
input values and an existing platform/restic setup. Do not treat it as live acceptance.
