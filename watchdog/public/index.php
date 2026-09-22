<?php
declare(strict_types=1);
require dirname(__DIR__) . '/common.php';
header('Content-Type: text/html; charset=UTF-8');
header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'");
try {
    $config = settings();
    $row = database($config)->query("SELECT state, checked_at, last_heartbeat FROM monitor WHERE id=1")->fetch(PDO::FETCH_ASSOC);
    $fresh = $row && heartbeatFresh($row['last_heartbeat'], (int)$config['max_age'], time());
    $cronFresh = $row && heartbeatFresh($row['checked_at'], 180, time());
    $state = $fresh && $cronFresh && $row['state'] === 'up' ? 'UP' : 'UNAVAILABLE';
    if ($state !== 'UP') http_response_code(503);
    echo '<!doctype html><html lang="en"><meta charset="utf-8"><title>Platform status</title>';
    echo '<h1>Developer Platform</h1><p>Status: ' . $state . '</p></html>';
} catch (Throwable $error) {
    publicFailure($error);
}
