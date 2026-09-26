<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/common.php';
require __DIR__ . '/mail.php';
require __DIR__ . '/backup.php';
$exitCode = 0;

$stage = 'loading configuration';
try {
    $config = settings();
    $stage = 'connecting to database';
    $db = database($config);
    $stage = 'acquiring cron lock';
    if ((int)$db->query("SELECT GET_LOCK('watchdog-cron', 0)")->fetchColumn() !== 1) {
        exit;
    }
    try {
        $stage = 'checking heartbeat';
        $row = $db->query('SELECT * FROM monitor WHERE id=1')->fetch(PDO::FETCH_ASSOC);
        if ($row === false) {
            throw new RuntimeException('Missing monitor row');
        }
        $now = time();
        $maxAge = (int)$config['max_age'];
        $healthy = heartbeatFresh($row['last_heartbeat'], $maxAge, $now);
        if ($config['health_url'] !== null) {
            $stage = 'checking HTTPS health endpoint';
            if (parse_url($config['health_url'], PHP_URL_SCHEME) !== 'https') {
                error_log('Health check configuration error: health_url must use HTTPS');
                throw new RuntimeException('Invalid health URL');
            }
            if (!function_exists('curl_init')) {
                error_log('Health check requires PHP cURL; enable it for the CLI PHP executable running cron');
                throw new RuntimeException('Missing cURL extension');
            }
            $curl = curl_init($config['health_url']);
            try {
                curl_setopt_array($curl, [
                    CURLOPT_HTTPGET => true, CURLOPT_RETURNTRANSFER => true,
                    CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 10,
                    CURLOPT_FOLLOWLOCATION => false,
                    CURLOPT_PROTOCOLS => CURLPROTO_HTTPS,
                ]);
                $result = curl_exec($curl);
                $code = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
                $healthPassed = $result !== false && $code >= 200 && $code < 300;
                $healthy = $healthy && $healthPassed;
            } finally {
                curl_close($curl);
            }
        }
        $state = $healthy ? 'up' : 'down';
        $stage = 'recording check result';
        $db->prepare('UPDATE monitor SET state=?,checked_at=UTC_TIMESTAMP() WHERE id=1')->execute([$state]);
        $db->prepare('INSERT INTO check_history(checked_at,state) VALUES (UTC_TIMESTAMP(),?)')->execute([$state]);
        if ($state !== $row['notified_state']) {
            $stage = 'sending notification';
            if (sendWatchdogMail($config, $state)) {
                $stage = 'recording notification success';
                $db->prepare('UPDATE monitor SET notified_state=? WHERE id=1')->execute([$state]);
            } else {
                error_log('Watchdog email failed; retry on next cron run');
            }
        }
        $stage = 'pruning check history';
        $db->exec('DELETE FROM check_history WHERE checked_at < UTC_TIMESTAMP() - INTERVAL 30 DAY');
    } finally {
        $db->query("SELECT RELEASE_LOCK('watchdog-cron')");
    }
} catch (Throwable $error) {
    // Raw exception messages may contain connection details or sensitive URLs.
    $detail = $error instanceof PDOException ? '; database_driver_code=' . (int)($error->errorInfo[1] ?? 0) : '';
    error_log('Watchdog cron failed while ' . $stage . '; error_type=' . get_class($error) . $detail);
    $exitCode = 1;
}

// Backup checks have their own state and still run after host-monitor errors.
try {
    $backupConfig = settings();
    if (backupEnabled($backupConfig)) checkBackup(database($backupConfig), $backupConfig);
} catch (Throwable $error) {
    error_log('Backup watchdog check failed');
    $exitCode = 1;
}
exit($exitCode);
