# Platform backups

Run deployment commands from the repository root.

## Start with the playbooks

Run these commands from the repository root on the **WSL/Ansible controller**.
Use the source backup inventory for backup tasks and the separate recovery
inventory for the disposable VM.

| Task | Playbook | Details |
| --- | --- | --- |
| Configure existing S3 repository access | [setup-backup.yml](ansible/setup-backup.yml) | [Credentials and initialization](#encrypted-s3-backup-repository-setup) |
| Install scheduled backups and alerts | [deploy-backup.yml](ansible/deploy-backup.yml) | [Schedule and watchdog prerequisites](#scheduled-backups-and-independent-backup-alerts) |
| Create a pre-backup marker and verified backup | [prepare-recovery-test.yml](ansible/prepare-recovery-test.yml) | [Source test preparation](#automate-marker-creation-and-the-source-backup) |
| Restore and test a fresh isolated VM | [restore-recovery.yml](ansible/restore-recovery.yml) | [Recovery inventory and safeguards](#restore-a-fresh-recovery-vm-with-ansible) |

### Backup setup and scheduling

Prepare `operations/backup/ansible/inventory.backup.yml` from its example and set
the source host. Configure the external watchdog's backup endpoint/schema/token
before deploying the schedule. Credentials are prompted privately.

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.yml \
  operations/backup/ansible/setup-backup.yml
ansible-playbook -i operations/backup/ansible/inventory.backup.yml \
  operations/backup/ansible/deploy-backup.yml
```

For a **new repository only**, follow the explicit initialization instructions
below. Existing repository access does not require initialization.

### Recovery drill

First create a marker and backup on the source:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.yml \
  operations/backup/ansible/prepare-recovery-test.yml \
  -e recovery_test_project=smoke
```

Use the printed snapshot ID and independent controller marker path in the
recovery inventory: `recovery_snapshot`, `recovery_marker_file`, and
`recovery_projects: [smoke]`. [Create/start a fresh VM](#local-recovery-vm-in-wsl-2)
and accept its verified SSH host key, then run:

```bash
ansible-playbook -i operations/backup/ansible/inventory.recovery.yml \
  operations/backup/ansible/restore-recovery.yml
```

The restore playbook refuses existing installations. Its fetched report must show
`result: passed` and `historical_data_verified: true` for a marker drill.
For an already-restored VM, [rerun only the check script](#run-tests-against-the-prepared-recovery-vm).
Do not rerun restoration to troubleshoot an acceptance failure.

The sections below explain configuration, recovery behavior, script usage, and
limitations. Manual restore commands are in the
[operations guide](../../docs/05-operations/backup-recovery.md#restore-into-an-isolated-installation).

## Encrypted S3 backup repository setup

[setup-backup.yml](ansible/setup-backup.yml) installs the distribution's `restic` package
and CA certificates on the existing Ubuntu platform host. It configures a
root-only restic command and verifies access to an encrypted S3 repository.
It runs independently of `deploy.yml` and does not redeploy or stop the platform.
See the [platform Ansible prerequisites](../../ansible/README.md) for the controller requirements.

The example uses the confirmed Hetzner destination:
`s3:https://hel1.your-objectstorage.com/eseidinger/developer-platform`, region
`hel1`. The bucket must already exist and the prefix must be reserved for this
repository. Review the destination before initialization; an S3 prefix is not an
access-control boundary. Use credentials with the necessary repository access.

From the local checkout on your Ansible controller:

```bash
cp operations/backup/ansible/inventory.backup.example.yml operations/backup/ansible/inventory.backup.yml
# Set ansible_host and ansible_user for node-01.
ansible-playbook -i operations/backup/ansible/inventory.backup.yml operations/backup/ansible/setup-backup.yml \
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
ansible-vault create operations/backup/ansible/backup-secrets.yml
# In the editor, define backup_s3_access_key, backup_s3_secret_key,
# and backup_restic_password. This path is ignored by Git.
ansible-playbook -i operations/backup/ansible/inventory.backup.yml operations/backup/ansible/setup-backup.yml \
  -e @operations/backup/ansible/backup-secrets.yml --ask-vault-pass
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
[delivery backlog](../../docs/04-development/delivery-backlog.md). Preserve platform
configuration, database roles/data, secrets and required service state in the
future recovery bundle; a repository alone does not cover that inventory.

Validate without deploying:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.example.yml operations/backup/ansible/setup-backup.yml --syntax-check
```

`--check` connects to inspect the host and previews package/file changes, but skips
all restic commands and repository creation/access checks. It still requires the
private input variables and validates an existing password if present. A successful
check run does not verify S3 permissions or password recovery.

References: [restic S3 repositories](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#s3-compatible-storage)
and [restic installation](https://restic.readthedocs.io/en/stable/020_installation.html).

## Scheduled backups and independent backup alerts

After repository setup, [deploy-backup.yml](ansible/deploy-backup.yml) installs the backup
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
3. Set `backup_watchdog_url` in `operations/backup/ansible/inventory.backup.yml` to the new endpoint,
   for example `https://status.example.com/backup.php`, and keep `backup_instance`
   stable (`node-01`). This identity scopes retention; changing it creates a new
   retention group. The endpoint's authenticated preflight must pass before the
   playbook enables any timer.
4. Deploy and request the first backup from the controller:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.yml operations/backup/ansible/deploy-backup.yml \
  -e backup_run_now=true
```

Enter the new backup token at the private prompt. Add `--ask-pass` / `--ask-become-pass`
if your SSH/sudo setup needs them. For unattended use, store `backup_watchdog_token`
in the same Vault-encrypted variables file used by setup and pass
`-e @operations/backup/ansible/backup-secrets.yml --ask-vault-pass`. The deployment does not need the
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

The operator-reported September 26, 2026 drill passed automated restore checks
including a pre-backup SQL marker. Precisely measured RPO/RTO, live S3 failure
tests, actual backup-alert receipt, and database-backed application acceptance
remain separate evidence requirements.
Exact-file readback is not an application restore exercise. Continue with
[backup and recovery](../../docs/05-operations/backup-recovery.md).

Local validation:

```bash
ansible-playbook -i operations/backup/ansible/inventory.backup.example.yml operations/backup/ansible/deploy-backup.yml --syntax-check
python3 -m unittest discover -s tests -v
php operations/watchdog/tests/backup.php
```

`--check` previews host installation without contacting the backup endpoint or
repository, enabling timers, or executing backups. It still requires configured
input values and an existing platform/restic setup. Do not treat it as live acceptance.

## Local recovery VM in WSL 2

Use [recovery-vm.py](scripts/recovery-vm.py) to create an empty Ubuntu 24.04
amd64 guest with its own kernel, disk, systemd and Docker installation. This needs
x86_64 WSL 2 with read/write access to `/dev/kvm`. Allocate enough memory to WSL
for the guest plus your existing workloads; the defaults are 4 virtual CPUs,
8192 MiB RAM and a sparse 100 GiB disk. Keep the VM in the WSL Linux filesystem.

Install tools inside WSL:

```bash
sudo apt-get update
sudo apt-get install qemu-system-x86 qemu-utils cloud-image-utils openssh-client
```

From the repository root in **WSL**, create a dedicated key if it does not
already exist (keep the existing key if prompted about overwriting):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/platform-recovery -C platform-recovery
```

Create the VM once using that SSH **public** key:

```bash
python3 operations/backup/scripts/recovery-vm.py create --public-key ~/.ssh/platform-recovery.pub
python3 operations/backup/scripts/recovery-vm.py start
```

For an existing VM, run only `start`; `create` refuses to overwrite its disk.
You can use another existing public key by changing `--public-key` and the matching
`ssh -i` path in the commands below. Creation never copies the private key.
It downloads Canonical's Ubuntu release image and checksum
manifest over HTTPS and verifies SHA-256 before publishing the VM directory.
This is checksum verification over HTTPS, not detached GPG signature verification.
`image.json` records the exact source URL and digest; the release URL can change
between new creations. Keep this metadata with restore-drill evidence.

The start command stays in the foreground. Leave that terminal open. In another
WSL terminal, inspect the serial console and connect after cloud-init provisions
the user:

```bash
tail -n 40 .runtime/recovery-vm/console.log
ssh -i ~/.ssh/platform-recovery -p 2222 recovery@127.0.0.1
```

Compare the SSH host-key fingerprint with the cloud-init console output on first
connection. In the guest, wait for first-boot configuration:

```bash
sudo cloud-init status --wait
```

The `recovery` account has passwordless sudo for Ansible and password login is
disabled. QEMU forwards only SSH, bound to WSL loopback. Guest outbound internet
access is available for S3 and package/image downloads. This is a separate
recovery installation, not an outbound network security boundary: do not launch
restored production notifications, scheduled backups, or applications with live
external side effects.

For Ansible, use a separate inventory (never the production inventory):

```yaml
developer_platform:
  hosts:
    recovery:
      ansible_host: 127.0.0.1
      ansible_port: 2222
      ansible_user: recovery
      ansible_ssh_private_key_file: ~/.ssh/platform-recovery
```

Store it under `.runtime/`. The VM helper provisions only the operating system and
SSH. Follow the [isolated recovery procedure](../../docs/05-operations/backup-recovery.md#restore-into-an-isolated-installation)
for platform prerequisites, original credentials, SQL import, and acceptance;
ordinary fresh-platform deployment is not a complete restore procedure. Configure
restic with existing S3 credentials/password and **do not initialize a repository**.
Leave heartbeat and scheduled backup deployment disabled in the recovery guest.

For browser access to guest HTTPS, open a tunnel from WSL once Caddy is running:

```bash
ssh -i ~/.ssh/platform-recovery -N -p 2222 -L 8443:127.0.0.1:443 recovery@127.0.0.1
```

Use test-domain hostname mappings and the corresponding TLS trust configuration.
Do not change production DNS. This drill verifies local recovery; public DNS/TLS
and Hetzner replacement-host provisioning require separate acceptance.

Shut down gracefully from another WSL terminal:

```bash
python3 operations/backup/scripts/recovery-vm.py stop
```

Alternatively, run `sudo shutdown -h now` inside the VM. The disk and restored
platform are preserved. To resume later, run `start` from WSL and reconnect by SSH.

Wait for the start terminal to exit before shutting down WSL or moving VM files.
The stop command requests ACPI poweroff; it does not forcibly kill a stuck guest.
Use the console log to diagnose shutdown problems. Guest reboot also exits QEMU;
run `start` again to boot it. No delete/reset command is provided, and `create`
refuses an existing destination. All disk, seed and log files are private under
Git-ignored `.runtime/recovery-vm/`; restored secrets remain on that disk.

Use `--cpus`, `--memory-mb` and `--ssh-port` on `start` to override resources;
`--disk-gb` applies at creation. For multiple drills, choose a different
`--directory` on all commands and a different SSH port on each running VM. Record
elapsed preparation and restoration time against the four-hour RTO.

References: [Ubuntu cloud images](https://cloud-images.ubuntu.com/releases/noble/release/),
[QEMU invocation](https://www.qemu.org/docs/master/system/invocation.html),
[cloud-init SSH configuration](https://cloudinit.readthedocs.io/en/stable/reference/yaml_examples/ssh.html).

### Remove the recovery VM or start a fresh drill

Run these commands in **WSL from the repository root**. First copy any test reports
you want to keep to `.runtime/recovery-evidence/`, as described in the
[test workflow](#run-tests-against-the-prepared-recovery-vm).

If the VM is running, request shutdown:

```bash
python3 operations/backup/scripts/recovery-vm.py stop
```

Wait for the QEMU start terminal to exit before continuing. If the VM is already
stopped, skip that command. Do not remove a disk while QEMU is using it.

To permanently remove the default recovery VM:

```bash
rm -r -- .runtime/recovery-vm
```

This deletes the VM disk, restored databases and secrets, cloud-init seed, console
log, and reports still stored inside the guest. It leaves separately copied
`.runtime/recovery-evidence/`, your SSH key, the production host, and the S3 backup
repository untouched. For a VM created with `--directory`, use that exact directory
instead after checking its contents and confirming its QEMU process has exited.

Alternatively, preserve the old VM before starting another drill:

```bash
mv .runtime/recovery-vm \
  ".runtime/recovery-vm-$(date -u +%Y%m%dT%H%M%SZ)"
```

The archived directory still contains restored secrets and consumes disk space.
Delete that specific directory with `rm -r --` when it is no longer needed.

After removing or moving the old directory, create and start a clean VM:

```bash
python3 operations/backup/scripts/recovery-vm.py create \
  --public-key ~/.ssh/platform-recovery.pub
python3 operations/backup/scripts/recovery-vm.py start
```

In another WSL terminal, remove the old SSH host-key entry for this local forwarded
port and connect to the new guest:

```bash
ssh-keygen -R '[127.0.0.1]:2222'
ssh -i ~/.ssh/platform-recovery -p 2222 recovery@127.0.0.1
```

Verify the new host-key fingerprint against `.runtime/recovery-vm/console.log`.
Only remove the old entry after intentionally replacing the VM. The fresh guest
needs repository access and the full isolated restore procedure again; it does
not inherit the previous installation.

## Automated recovery acceptance checks

[test-recovery.py](scripts/test-recovery.py) checks an already-restored, running
installation. It does not restore files, import SQL, provision the VM, or reapply
projects. It requires the restored `.env`, `scripts`/Compose files, working local
API, and `.runtime/bin/kubectl` plus the regenerated admin kubeconfig. Recovery
settings must be `EDGE_BIND_IP=127.0.0.1`, `PLATFORM_DOMAIN=platform.localhost`,
and `APPS_DOMAIN=apps.localhost`. Leave production alert senders disabled.

### Run tests against the prepared recovery VM

1. **WSL, repository root:** start the existing VM if it is stopped. Leave this
   terminal running; skip this command if QEMU is already running.

   ```bash
   python3 operations/backup/scripts/recovery-vm.py start
   ```

2. **Another WSL terminal, repository root:** copy the current helper and connect.
   Repeat the copy after script updates; `/tmp` may be cleared when the VM reboots.

   ```bash
   scp -i ~/.ssh/platform-recovery -P 2222 \
     operations/backup/scripts/test-recovery.py recovery@127.0.0.1:/tmp/test-recovery.py
   ssh -i ~/.ssh/platform-recovery -p 2222 recovery@127.0.0.1
   ```

3. **Inside the recovery VM:** wait for boot configuration, then run the suite
   against the already-restored `smoke` project and verified bundle. The script
   prints the report path and exits nonzero on failure.

   ```bash
   sudo cloud-init status --wait
   sudo python3 /tmp/test-recovery.py check \
     --platform-dir /opt/developer-platform \
     --bundle /root/platform-recovery/bundle \
     --project smoke
   ```

   If this is a fresh VM, first complete the
   [isolated restore and project reapply](../../docs/05-operations/backup-recovery.md#restore-into-an-isolated-installation).
   For an existing restored VM, allow the services time to restart. The suite
   retries API readiness and ingress, and allows up to 180 seconds per monitoring
   check for Prometheus readiness, Grafana health, and scrape convergence. Persistent
   failures identify the specific monitoring check in the report. Inspect `sudo docker compose -f /opt/developer-platform/compose.yaml ps -a`
   if necessary, then rerun the suite once the cause is resolved.

4. **Inside the VM:** inspect the exact report path printed by the runner:

   ```bash
   sudo cat /opt/developer-platform/.runtime/recovery/checks-REPLACE_WITH_ID.json
   ```

   A successful run reports `"result": "passed"`. Without a pre-backup marker,
   `"historical_data_verified": false` is expected; it is not full data-recovery
   acceptance. On failure, use `failed_stage` to investigate before rerunning.
   Every run creates a separate report, preserving earlier evidence.

5. **WSL, repository root:** save the report independently of the VM, replacing
   the filename with the one printed by the runner:

   ```bash
   mkdir -p .runtime/recovery-evidence
   (umask 077
    ssh -i ~/.ssh/platform-recovery -p 2222 recovery@127.0.0.1 \
      'sudo cat /opt/developer-platform/.runtime/recovery/checks-REPLACE_WITH_ID.json' \
      > .runtime/recovery-evidence/checks-REPLACE_WITH_ID.json)
   ```

6. **WSL, repository root:** shut down the VM after collecting evidence:

   ```bash
   python3 operations/backup/scripts/recovery-vm.py stop
   ```

Wait for the QEMU terminal to exit. Start it again with the same `start` command
for subsequent test runs; no recreation or reimport is needed.

### Checks and report interpretation

The suite verifies bundle checksums, API readiness/catalog membership, deployment
rollout, HTTP ingress, Prometheus readiness/scrape health and Grafana database
health. A temporary restricted pod uses the existing project database secret to
verify the workload network path, database identity, transactional write/read,
and absence of CONNECT privilege on the platform catalog. It pulls the configured
PostgreSQL image directly; it does not use the failing k3d image-import path.
The test table is temporary and rolled back. Successful pods are deleted. Failed pods are retained and their names recorded
in the report for diagnosis; delete them after inspection. If the process is
forcibly killed, inspect/remove any leftover
`recovery-check-*` pod in the tested namespace.

Every check run writes a new private JSON report under
`/opt/developer-platform/.runtime/recovery/checks-<id>.json`, or the new file
specified with `--report`. Exit status is nonzero on failure. Reports contain
passed stages, failed stage, backup identity, and test start/end timestamps, but
no credentials or raw command output. Each network/command wait is bounded.
Image-pull/configuration failures fail early. The runner does not send alerts.

### Verify data written before backup

On the **source host**, explicitly seed a marker in an existing project's database
before taking a new backup. This creates a uniquely named persistent table and
one row, using that project's derived credentials through the API container:

```bash
sudo python3 /path/to/test-recovery.py seed-marker --project smoke \
  --marker /root/smoke-marker.json
sudo systemctl start platform-backup.service
```

Copy the marker receipt to independent storage and then to the recovery VM.
Keep the original receipt outside the backup: it defines what must be recovered.
A receipt with `seeded: false` is not valid evidence; a failed seeding run must be
investigated. Seeding never overwrites a receipt. The marker table intentionally
remains for backup; remove it only after completing the drill, using the exact
name recorded in the receipt.

Restore the **new** verified snapshot into a fresh isolated recovery installation,
then run there:

```bash
sudo python3 /tmp/test-recovery.py check --project smoke \
  --marker /root/smoke-marker.json
```

The pod must find the expected row and the backup capture must postdate the
receipt. Missing table/row, a mismatched project, or invalid receipt fails the run.
Without `--marker`, a passing report explicitly sets `historical_data_verified`
to false. This marker proves SQL data survival, not a database-backed application's
end-to-end transaction behavior. Network denial to other namespaces/internet,
public DNS/TLS, live alert delivery, and full recovery-time/data-loss targets
remain separate checks. Test duration is **not** total RTO; record VM preparation,
restoration start and simulated failure timestamps separately.

### Local tests for the prepared scripts

Run these in **WSL from the repository root** to check the helpers themselves.
They do not boot a VM, contact S3, or execute live recovery checks:

```bash
python3 -m unittest discover -s operations/backup/tests -v
python3 -m compileall -q operations/backup/scripts
python3 operations/backup/scripts/recovery-vm.py --help
python3 operations/backup/scripts/test-recovery.py --help
```

The optional encrypted-restic integration test is skipped unless
`RESTIC_TEST_BINARY` points to a local restic executable. Passing local tests does
not replace running the acceptance suite inside the restored VM.

## Restore a fresh recovery VM with Ansible

[restore-recovery.yml](ansible/restore-recovery.yml) automates the restore procedure
for the VM created by `recovery-vm.py`. Use a **fresh VM**: the playbook refuses an
existing `/opt/developer-platform`, recovery staging directory, platform sender
timers, or Docker containers/volumes. It targets only the `recovery` inventory
group and requires Ubuntu 24.04+ amd64, hostname `platform-recovery`, and SSH at
`127.0.0.1:2222`. It does not support production hosts or an in-place restore.

In **WSL, repository root**, after creating/starting the VM and accepting its SSH
host key:

```bash
cp operations/backup/ansible/inventory.recovery.example.yml \
  operations/backup/ansible/inventory.recovery.yml
```

Edit the copied inventory: set `recovery_snapshot` to an explicit verified snapshot
ID (for example, the full ID corresponding to `c03a2bcc` in the first drill), and
select `recovery_projects`. The default is `[smoke]`. Review stored project images
before selecting them: starting applications can cause external side effects.
An optional `recovery_marker_file` is a controller-side path to the independently
saved receipt; when using it, select only the matching project.

Run from **WSL**:

```bash
ansible-playbook \
  -i operations/backup/ansible/inventory.recovery.yml \
  operations/backup/ansible/restore-recovery.yml
```

Enter S3 credentials and the **existing** repository password at the private
prompts. There is no repository initialization, prune, or backup scheduling step.
Repository/region can be overridden by inventory; defaults match the existing
Hetzner repository. Snapshots must carry `developer-platform,verified` tags and
belong to `node-01`. A short ID is resolved to exactly one full snapshot ID.

The playbook installs restic and Docker, retrieves the bundle, verifies checksums,
restores the original credentials, applies loopback/test domains, imports SQL,
restores Caddy/Grafana volumes, installs pinned Kubernetes tooling, bootstraps the
cluster, reapplies selected catalog specs, and runs `test-recovery.py` for each
selected project. Caddy uses internal TLS for test domains; Grafana alerting/SMTP
and Alertmanager delivery are disabled. Host service/config archives are preserved
in the bundle but not installed, so production heartbeat and backup timers stay
absent. PostgreSQL and workload image versions come from the restored files/specs.

SQL import keeps private stdout/stderr under
`/opt/developer-platform/.runtime/recovery/`. Only the known bootstrap duplicate
errors for role `postgres` and database `platform` are accepted; any other
nonempty diagnostic or repeated duplicate stops restoration. Service volumes may
contain image-created directories but must contain no files/links before restore.
The entire process is bounded by Ansible asynchronous task timeouts.

Acceptance reports are fetched into the controller's Git-ignored
`.runtime/recovery-evidence/<inventory-host>/<run-timestamp>/` directory, including
reports from failed acceptance suites. Earlier restoration failures stop before
acceptance and require inspection of the VM/private logs. The verified snapshot
selection is recorded on the VM in `/root/platform-recovery/snapshot.json`.

This is deliberately a **one-shot** restore. If restoration fails, inspect the
cause, then [recreate the VM](#remove-the-recovery-vm-or-start-a-fresh-drill) before
rerunning. It never automatically deletes partially restored data. Once restored,
use the [check script](#run-tests-against-the-prepared-recovery-vm) for repeat tests.
Without a marker receipt, passing checks do not establish historical data recovery.
Record whole-drill start/completion separately from acceptance-test duration.

Validate playbook syntax without connecting:

```bash
ansible-playbook \
  -i operations/backup/ansible/inventory.recovery.example.yml \
  operations/backup/ansible/restore-recovery.yml --syntax-check
```

`--check` is refused because a simulated restore cannot validate subsequent SQL,
cluster or application checks. Local helper tests cover checksum/path safeguards
and SQL diagnostic classification; they do not prove a live end-to-end restore.

### Automate marker creation and the source backup

The [prepare-recovery-test.yml](ansible/prepare-recovery-test.yml) playbook runs
against the **source host**, using the existing backup inventory and installed
backup service. It creates one uniquely named table/row in the selected project,
saves a separate marker receipt on the controller before backup, starts the managed
backup service, and verifies that the successful capture occurred after marker
commit. It does not need S3/password prompts because backup access is already
configured on the source.

From **WSL, repository root**:

```bash
ansible-playbook \
  -i operations/backup/ansible/inventory.backup.yml \
  operations/backup/ansible/prepare-recovery-test.yml \
  -e recovery_test_project=smoke
```

The source project must exist and its platform API container must be running.
Normal backup behavior applies, including brief Caddy/Grafana interruption and
retention. Each run intentionally creates a new marker and private evidence
directory; this is a test action, not an idempotent configuration playbook.
The marker remains in the source database until explicitly cleaned up after the
drill. No production data or backup is automatically deleted by the marker helper.

The final output provides the full snapshot ID and controller marker path. Set
`recovery_snapshot`, `recovery_projects: [smoke]`, and `recovery_marker_file` in the
separate recovery inventory, then run `restore-recovery.yml` against a fresh VM.
Use the absolute controller marker path. The acceptance report must show both
`result: passed` and `historical_data_verified: true`.

If a backup was already running before the marker commit, the timestamp check
rejects it. Let it finish and run a new backup; do not accept the old snapshot as
marker evidence. Source receipts and captured status remain available under
`.runtime/recovery-evidence/<inventory-host>/recovery-test-<unique-id>/` for diagnosis.
A pending notification may produce a nonzero service exit even with a verified
backup; the playbook reports the service exit code separately from snapshot proof.
