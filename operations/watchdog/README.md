# External PHP/MySQL watchdog

Requirements: independent web hosting, PHP >=8.2, PDO-MySQL, a cron job running
every minute, and either working PHP mail() delivery or an SMTP account.
PHP cURL with SMTP/SMTPS support and a working CA trust store is required for
SMTP; cURL is also required for optional HTTPS checks.

For hosting with SSH and SCP, the [Ansible deployment playbook](ansible/README.md#external-watchdog-via-scp)
automates the file upload, private configuration upload, and optional cron job.

1. Upload the contents of `operations/watchdog/src/` to the web host’s `watchdog/` directory.
   Set DocumentRoot exclusively to
   `watchdog/public/`. `common.php`, `config.local.php`, and `cron.php`
   must remain outside publicly accessible directories.
2. Copy `config.example.php` to `config.local.php` in the uploaded directory. Configure a separate MySQL
   user and database, and a token containing at least 32 random characters.
   Do not use the example values.
3. Run `php /absolute/path/watchdog/import-schema.php` on the hosting server.
   It imports `schema.sql` using the database credentials in `config.local.php`.
   Create the database and user first, with CREATE, INSERT, and INDEX permissions
   for setup (plus SELECT, UPDATE, and DELETE for normal operation). Rerunning the
   importer preserves existing monitor state and history. It does not create the
   database/user or migrate an older table structure. MySQL DDL is not atomic;
   after fixing an import failure, rerun the script to complete setup.
4. Configure the hosting cron service to run
   `php /absolute/path/watchdog/cron.php` every minute.
5. Serve the status page over HTTPS. The Authorization header must be forwarded
   to PHP; verify this with the hosting provider.
6. On the Docker host, create `/etc/developer-platform/watchdog.env` with mode 0600:
   `WATCHDOG_URL=https://status.example.com/heartbeat.php` and
   `WATCHDOG_TOKEN=...`.
7. Install `operations/heartbeat/scripts/heartbeat.py` as
   `/usr/local/lib/developer-platform/heartbeat.py` (mode 0644, parent directory 0755).
   Copy both units from `operations/heartbeat/systemd/` to `/etc/systemd/system/`.
   Run `systemctl daemon-reload` and
   `systemctl enable --now platform-heartbeat.timer`.

Steps 6–7 can be automated with the [heartbeat Ansible playbook](../heartbeat/README.md),
which also installs the sender script in a location readable by the systemd service.

If schema import fails, the importer reports the failing stage, SQLSTATE, driver
error code, and a suggested check without printing database credentials. Check
`php -m` for `pdo_mysql` in the CLI PHP installation. The database must already
exist; use the database hostname supplied by your hosting provider in the DSN.
Error codes are described in the MySQL [server](https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html)
and [client](https://dev.mysql.com/doc/mysql-errors/8.0/en/client-error-reference.html) references.

The heartbeat endpoint accepts only authenticated POST requests and atomically
limits valid writes to once every 30 seconds. Unauthenticated requests do not
open a database connection. Add general HTTP rate limiting at the hosting provider
if available.

Cron combines heartbeat freshness with an optional fixed HTTPS health check.
No HTTP target address is taken from requests. Redirects are disabled.
The optional health check uses GET; the target must return a 2xx response.
Email is sent when status changes; failed mail or SMTP handoffs are retried on
the next run. Successful handoff means acceptance by the mail server, not
guaranteed delivery. SMTP failures do not fall back to PHP mail().

To use SMTP, add the `smtp` settings from `config.example.php` to your private
`config.local.php`, set `mail_transport` to `smtp`, and enter your provider’s
host, port, username, and password in `smtp.password`. Use `starttls` with port
587 or `tls` with port 465, as specified by your provider. TLS and certificate
verification are mandatory. Use a provider app password if required. Existing
configurations without `mail_transport` continue to use PHP mail(). The Ansible
playbook uploads this file when `watchdog_config_file` is supplied; it does not
generate configuration or SMTP credentials.

Check history is retained for 30 days. The status page does not disclose internal
hosts, error details, or secrets. Freshness is also checked when the page is viewed.

After setup, test correct and incorrect tokens, rate limiting, heartbeat loss,
recovery email, and a failed cron job. Without access to the hosting environment,
actual email delivery and a public installation have not been tested.

## Repository layout and tests

The PHP application, configuration, and SQL schema live in `src/`; `ansible/` contains deployment
playbooks and inventory examples, `scripts/` contains the integration runner, and `tests/` contains
the PHP checks and disposable container stack.

From the repository root:

```bash
php operations/watchdog/tests/watchdog.php
php -d curl.cainfo=/tmp/watchdog-smtp-cert.pem -d sendmail_path=/bin/true operations/watchdog/tests/watchdog-mail.php
python3 operations/watchdog/scripts/test-watchdog.py
```

## Independent backup monitoring

`public/backup.php` accepts authenticated backup events using a separate
`backup_token` in private `config.local.php`. Empty/unset leaves backup checks
disabled for existing installations. To enable, upload the current release,
re-run the CLI schema importer, then set a random token distinct from the host
heartbeat token. The additive `backup_monitor` table preserves existing host
state. Use the same new token for the [scheduled backup playbook](../backup/README.md#scheduled-backups-and-independent-backup-alerts).

The existing cron now checks both channels independently. Backup events never
update `monitor.last_heartbeat`; host heartbeats never update `backup_monitor`.
Backup emails are labeled **BACKUP DOWN/UP** and use the existing mail recipients.
A first DOWN/no-backup message is expected before a verified snapshot is reported.

Authenticated GET returns the protocol/age/timeout configuration without changing
freshness. POST accepts at most 4096 bytes of JSON: `run_id` (32 lowercase hex
characters), `started` (UTC Unix seconds), and `event` (`start`, `success`, or
`failure`). Success additionally requires a full 64-hex `snapshot` ID. Future
start times beyond five minutes are rejected. Duplicate completions are safe;
older runs and contradictory completions return 409. A completion can arrive
without its start after a transport outage. Only success updates capture freshness.

Backup health becomes down for explicit failure, missing success, a run older
than two hours, or last successful capture older than 24 hours. Starting a new
run does not clear the previous failure. Recovery requires a fresh verified success.
The platform runner queues undelivered events locally; cron retries failed mail
handoff without marking it delivered. This does not independently monitor failure
of the external watchdog host or its cron.

Run `php operations/watchdog/tests/backup.php` for pure transition/freshness tests.
The disposable integration test also covers separate-token denial, replay handling,
host/backup independence, overdue/stalled conditions and repeat schema import.
Mail remains simulated in that test; verify actual BACKUP DOWN and UP receipt.
