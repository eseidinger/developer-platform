# External PHP/MySQL watchdog

Requirements: independent web hosting, PHP >=8.1, PDO-MySQL, a cron job running
every minute, and working PHP mail() delivery; cURL for optional HTTPS checks.

1. Upload the directory to the web host. Set DocumentRoot exclusively to
   `watchdog/public/`. `common.php`, `config.local.php`, and `cron.php`
   must remain outside publicly accessible directories.
2. Copy `config.example.php` to `config.local.php`. Configure a separate MySQL
   user and database, and a token containing at least 32 random characters.
   Do not use the example values.
3. Import `schema.sql` into the watchdog database once.
4. Configure the hosting cron service to run
   `php /absolute/path/watchdog/cron.php` every minute.
5. Serve the status page over HTTPS. The Authorization header must be forwarded
   to PHP; verify this with the hosting provider.
6. On the Docker host, create `/etc/developer-platform/watchdog.env` with mode 0600:
   `WATCHDOG_URL=https://status.example.com/heartbeat.php` and
   `WATCHDOG_TOKEN=...`.
7. Copy both units from `infrastructure/systemd/` to `/etc/systemd/system/`;
   adjust the installation path in ExecStart if necessary.
   Run `systemctl daemon-reload` and
   `systemctl enable --now platform-heartbeat.timer`.

The heartbeat endpoint accepts only authenticated POST requests and atomically
limits valid writes to once every 30 seconds. Unauthenticated requests do not
open a database connection. Add general HTTP rate limiting at the hosting provider
if available.

Cron combines heartbeat freshness with an optional fixed HTTPS health check.
No HTTP target address is taken from requests. Redirects are disabled.
The optional health check uses HEAD; the target must support it with a 2xx response.
Email is sent when status changes; failed mail() handoffs are retried on the next
run. A successful mail() return value only means acceptance by the local mailer,
not guaranteed delivery.

Check history is retained for 30 days. The status page does not disclose internal
hosts, error details, or secrets. Freshness is also checked when the page is viewed.

After setup, test correct and incorrect tokens, rate limiting, heartbeat loss,
recovery email, and a failed cron job. Without access to the hosting environment,
actual email delivery and a public installation have not been tested.
