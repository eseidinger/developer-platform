<?php
declare(strict_types=1);
require dirname(__DIR__) . '/common.php';
header('Cache-Control: no-store');
try {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        header('Allow: POST'); http_response_code(405); exit;
    }
    $config = settings();
    $authorization = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (!hash_equals('Bearer ' . $config['token'], $authorization)) {
        http_response_code(401); exit;
    }
    $db = database($config);
    // Atomic throttling across PHP workers; valid requests at most once per 30 seconds.
    $changed = $db->exec("UPDATE monitor SET last_heartbeat=UTC_TIMESTAMP()
        WHERE id=1 AND (last_heartbeat IS NULL
        OR last_heartbeat <= UTC_TIMESTAMP() - INTERVAL 30 SECOND)");
    if ($changed === 0) {
        header('Retry-After: 30'); http_response_code(429); exit;
    }
    http_response_code(204);
} catch (Throwable $error) {
    publicFailure($error);
}
