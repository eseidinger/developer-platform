<?php
declare(strict_types=1);
require dirname(__DIR__) . '/common.php';
require dirname(__DIR__) . '/backup.php';
header('Cache-Control: no-store');
try {
    if (!in_array($_SERVER['REQUEST_METHOD'], ['GET', 'POST'], true)) {
        header('Allow: GET, POST'); http_response_code(405); exit;
    }
    $config = settings();
    if (!backupEnabled($config)) { http_response_code(503); exit; }
    validateBackupConfig($config);
    if (!hash_equals('Bearer ' . $config['backup_token'], $_SERVER['HTTP_AUTHORIZATION'] ?? '')) {
        http_response_code(401); exit;
    }
    $db = database($config);
    if ($_SERVER['REQUEST_METHOD'] === 'GET') {
        // Preflight checks configuration and migration without refreshing backup freshness.
        if ($db->query('SELECT id FROM backup_monitor WHERE id=1')->fetchColumn() === false) {
            throw new RuntimeException('Missing backup monitor');
        }
        header('Content-Type: application/json');
        echo '{"protocol":1,"max_age":86400,"timeout":7200}';
        exit;
    }
    $body = file_get_contents('php://input', false, null, 0, 4097);
    if ($body === false || strlen($body) > 4096) { http_response_code(413); exit; }
    try {
        $data = json_decode($body, true, 16, JSON_THROW_ON_ERROR);
        if (!is_array($data)) throw new InvalidArgumentException('Object required');
        validateBackupEvent($data, time());
    } catch (JsonException | InvalidArgumentException $error) {
        http_response_code(400); exit;
    }
    $db->beginTransaction();
    try {
        $row = $db->query('SELECT * FROM backup_monitor WHERE id=1 FOR UPDATE')->fetch(PDO::FETCH_ASSOC);
        if ($row === false) throw new RuntimeException('Missing backup monitor');
        $next = applyBackupEvent($row, $data);
        if ($next === null) {
            $db->rollBack(); http_response_code(409); exit;
        }
        $db->prepare('UPDATE backup_monitor SET run_id=?,started=?,running=?,outcome=?,last_capture=?,snapshot=?,received_at=UTC_TIMESTAMP() WHERE id=1')
            ->execute([$next['run_id'], $next['started'], $next['running'], $next['outcome'], $next['last_capture'], $next['snapshot']]);
        $db->commit();
    } finally {
        if ($db->inTransaction()) $db->rollBack();
    }
    http_response_code(204);
} catch (Throwable $error) {
    // Do not expose request bodies, tokens, DSNs or raw driver messages.
    error_log('Backup signal processing failed');
    http_response_code(503);
}
