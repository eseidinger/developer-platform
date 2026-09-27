# Alertmanager SMTP deployment

Configure the existing platform Alertmanager from an Ansible inventory. Run
controller commands from the repository root with ansible-core >= 2.16.
The target needs an existing platform installation, Docker Compose, SSH and sudo
(or root) access. No additional Ansible collections are required.

## Configure and deploy

```bash
cp operations/alertmanager/ansible/inventory.alertmanager.example.yml operations/alertmanager/ansible/inventory.alertmanager.yml
```

Edit the copied inventory: SSH host/user, installation path, SMTP host/port,
username, sender, recipients and response owner. Use `starttls` for STARTTLS
(normally port 587), or `implicit_tls` for TLS from connection start (normally
port 465). Certificate verification stays enabled. The response owner identifies
who handles these alerts; it does not configure an escalation service.
Set recipients to the intended operational mailbox(es); all routed alerts and
recovery notifications go there.

```bash
ansible-playbook -i operations/alertmanager/ansible/inventory.alertmanager.yml operations/alertmanager/ansible/deploy-alertmanager.yml
```

Enter the SMTP password at the hidden prompt. Add `--ask-become-pass` if sudo
requires a password, and `--ask-pass` if SSH requires one. For automation, create
an encrypted file with `ansible-vault create operations/alertmanager/ansible/smtp-secrets.yml`,
containing `alertmanager_smtp_password`, then add
`--ask-vault-pass -e @operations/alertmanager/ansible/smtp-secrets.yml`.
Do not pass passwords directly on the command line or store them in the inventory.

The playbook validates a temporary candidate using this checkout's pinned
Alertmanager image before installing it. The password is in a separate
`infrastructure/monitoring/private/smtp-password` file, mode 0600, readable by
the container's UID 65534; its directory is 0700. Secret tasks suppress output
and diffs. Temporary candidates are removed even after validation failure.

The playbook installs this checkout's monitoring Compose definition and selects
the private directory in the target's existing `.env`. Only Alertmanager is
recreated when settings change. Other services are not reconciled by this
playbook, although a later full deployment uses the updated Compose definition.
Rerun with the same password to reconcile settings; supply a new password to rotate.
Readiness establishes process health, not SMTP delivery.

`--check` validates inventory inputs only and skips remote deployment/validation.
For syntax only:

```bash
ansible-playbook -i operations/alertmanager/ansible/inventory.alertmanager.example.yml operations/alertmanager/ansible/deploy-alertmanager.yml --syntax-check
```

## Verify actual email delivery

Deployment enables real notifications, including any existing firing alerts.
On the target, in a root shell:

```bash
cd /opt/developer-platform
docker compose exec -T alertmanager amtool --alertmanager.url=http://127.0.0.1:9093 alert add \
  alertname=PlatformEmailTest job=manual severity=info \
  --annotation=summary='Operator-requested SMTP delivery test' \
  --end="$(date -u -d '+2 minutes' +%Y-%m-%dT%H:%M:%SZ)"
```

Confirm a FIRING email after the configured group wait (default 30 seconds).
The synthetic alert expires after two minutes; confirm a RESOLVED email after
the next group interval (default five minutes). If repeating the test, wait for
resolution or use a distinct alert name. No workload outage is needed.

To inspect delivery failures privately on the target:

```bash
docker compose logs --since=10m alertmanager
docker compose exec -T alertmanager wget -q -O - http://127.0.0.1:9093/metrics
```

Look for notification errors and `alertmanager_notifications_failed_total`.
Do not paste unredacted logs or config into shared channels. This tests
Alertmanager-to-email delivery, not Prometheus rule evaluation or independent
watchdog failure detection.

Record deployed revision, environment, response owner, send/receipt times for
both emails and any failures under OPS-007-T01 in the
[backlog](../../docs/04-development/delivery-backlog.md#current-monitoring-progress).
The playbook never marks live acceptance complete.

## Backup and recovery

Private config is under `infrastructure`, already captured by the encrypted
platform backup. Bootstrap source archives exclude the controller's private
directory and preserve the target's files and `.env` selection. Local inventory
and secrets paths are ignored by Git.

The isolated recovery helper resets the config directory to the notification-free
default, so restored SMTP credentials do not send production email during drills.
Repeat backup/restore acceptance after deploying this new secret state.
To disable SMTP manually, set `ALERTMANAGER_CONFIG_DIR=.` in the target `.env`
and recreate Alertmanager; the tracked default receiver has no delivery target.

SMTP field reference: [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/).
