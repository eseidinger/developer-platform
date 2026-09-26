<?php
declare(strict_types=1);

function backupEnabled(array $config): bool {
    return isset($config['backup_token']) && $config['backup_token'] !== '';
}
function validateBackupConfig(array $config): void {
    if (!is_string($config['backup_token'] ?? null) || strlen($config['backup_token']) < 32
        || str_starts_with($config['backup_token'], 'replace-')
        || hash_equals($config['token'], $config['backup_token'])) {
        throw new RuntimeException('Configure a separate backup token');
    }
}
function backupReason(array $row, int $now, int $maxAge = 86400, int $timeout = 7200): string {
    if ((bool)$row['running'] && $now - (int)$row['started'] > $timeout) return 'stalled';
    if ($row['outcome'] === 'failure') return 'failed';
    if ($row['last_capture'] === null) return 'no-backup';
    if ((int)$row['last_capture'] > $now || $now - (int)$row['last_capture'] > $maxAge) return 'overdue';
    return 'up';
}
function validateBackupEvent(array $data, int $now): void {
    if (!is_string($data['run_id'] ?? null) || !preg_match('/\A[0-9a-f]{32}\z/', $data['run_id'])
        || !is_int($data['started'] ?? null) || $data['started'] <= 0 || $data['started'] > $now + 300
        || !in_array($data['event'] ?? '', ['start', 'success', 'failure'], true)
        || ($data['event'] === 'success' && (!is_string($data['snapshot'] ?? null)
            || !preg_match('/\A[0-9a-f]{64}\z/', $data['snapshot'])))) {
        throw new InvalidArgumentException('Invalid backup event');
    }
}
// Pure transition logic: replay and late events cannot erase newer failures.
function applyBackupEvent(array $row, array $data): ?array {
    $started = (int)($row['started'] ?? 0);
    if ($data['started'] < $started) return null;
    if ($data['started'] === $started) {
        if ($data['run_id'] !== $row['run_id']) return null;
        if (!(bool)$row['running']) {
            // Duplicate completion is harmless; start or contradictory completion is stale.
            return $data['event'] === $row['outcome'] ? $row : null;
        }
        if ($data['event'] === 'start') return $row;
    }
    $row['run_id'] = $data['run_id'];
    $row['started'] = $data['started'];
    $row['running'] = $data['event'] === 'start' ? 1 : 0;
    if ($data['event'] !== 'start') $row['outcome'] = $data['event'];
    if ($data['event'] === 'success') {
        $row['last_capture'] = $data['started'];
        $row['snapshot'] = $data['snapshot'];
    }
    return $row;
}
function checkBackup(PDO $db, array $config): void {
    validateBackupConfig($config);
    if ((int)$db->query("SELECT GET_LOCK('watchdog-backup-cron', 0)")->fetchColumn() !== 1) return;
    try {
        // Serialize with ingestion so a concurrent failure cannot receive a recovery notification.
        $db->beginTransaction();
        $row = $db->query('SELECT * FROM backup_monitor WHERE id=1 FOR UPDATE')->fetch(PDO::FETCH_ASSOC);
        if ($row === false) throw new RuntimeException('Missing backup monitor row');
        $reason = backupReason($row, time());
        $state = $reason === 'up' ? 'up' : 'down';
        $db->prepare('UPDATE backup_monitor SET state=?,checked_at=UTC_TIMESTAMP() WHERE id=1')->execute([$state]);
        if ($state !== $row['notified_state']) {
            if (sendWatchdogMail($config, $state, 'backup', $reason)) {
                $db->prepare('UPDATE backup_monitor SET notified_state=? WHERE id=1')->execute([$state]);
            } else {
                error_log('Backup notification failed; retry on next cron run');
            }
        }
        $db->commit();
    } finally {
        if ($db->inTransaction()) $db->rollBack();
        $db->query("SELECT RELEASE_LOCK('watchdog-backup-cron')");
    }
}
