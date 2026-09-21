<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/common.php';
$config = settings();
$db = database($config);
if ((int)$db->query("SELECT GET_LOCK('watchdog-cron', 0)")->fetchColumn() !== 1) exit;
try {
    $row = $db->query('SELECT * FROM monitor WHERE id=1')->fetch(PDO::FETCH_ASSOC);
    $healthy = heartbeatFresh($row['last_heartbeat'], (int)$config['max_age'], time());
    if ($config['health_url'] !== null) {
        if (parse_url($config['health_url'], PHP_URL_SCHEME) !== 'https') {
            throw new RuntimeException('Health URL must use HTTPS');
        }
        $curl = curl_init($config['health_url']);
        curl_setopt_array($curl, [
            CURLOPT_NOBODY => true, CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 10,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS,
        ]);
        $result = curl_exec($curl);
        $code = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
        curl_close($curl);
        $healthy = $healthy && $result !== false && $code >= 200 && $code < 300;
    }
    $state = $healthy ? 'up' : 'down';
    $db->prepare('UPDATE monitor SET state=?,checked_at=UTC_TIMESTAMP() WHERE id=1')->execute([$state]);
    $db->prepare('INSERT INTO check_history(checked_at,state) VALUES (UTC_TIMESTAMP(),?)')->execute([$state]);
    if ($state !== $row['notified_state']) {
        foreach (['mail_to', 'mail_from'] as $field) {
            if (!filter_var($config[$field], FILTER_VALIDATE_EMAIL)) {
                throw new RuntimeException('Invalid mail address');
            }
        }
        if (mail($config['mail_to'], 'Developer Platform: ' . strtoupper($state),
                 'The external watchdog reports: ' . $state,
                 'From: ' . $config['mail_from'])) {
            $db->prepare('UPDATE monitor SET notified_state=? WHERE id=1')->execute([$state]);
        } else {
            error_log('Watchdog email failed; retry on next cron run');
        }
    }
    $db->exec('DELETE FROM check_history WHERE checked_at < UTC_TIMESTAMP() - INTERVAL 30 DAY');
} finally {
    $db->query("SELECT RELEASE_LOCK('watchdog-cron')");
}
