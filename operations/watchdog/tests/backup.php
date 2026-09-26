<?php
require __DIR__ . '/../src/backup.php';
$now = 1800000000;
$row = ['run_id' => null, 'started' => null, 'running' => 0, 'outcome' => 'unknown', 'last_capture' => null, 'snapshot' => null];
function expect($actual, $expected): void {
    if ($actual !== $expected) throw new RuntimeException('Backup state check failed');
}
expect(backupReason($row, $now), 'no-backup');
$event = ['run_id' => str_repeat('a', 32), 'started' => $now - 100, 'event' => 'success', 'snapshot' => str_repeat('b', 64)];
validateBackupEvent($event, $now);
$row = applyBackupEvent($row, $event);
expect(backupReason($row, $now), 'up');
expect(backupReason($row, $now + 86300), 'up');
expect(backupReason($row, $now + 86301), 'overdue');
expect(applyBackupEvent($row, $event), $row);
expect(applyBackupEvent($row, array_replace($event, ['event' => 'start'])), null);
$row = applyBackupEvent($row, ['run_id' => str_repeat('c',32), 'started' => $now, 'event' => 'start']);
expect(backupReason($row, $now + 7200), 'up');
expect(backupReason($row, $now + 7201), 'stalled');
$row = applyBackupEvent($row, ['run_id' => str_repeat('c',32), 'started' => $now, 'event' => 'failure']);
expect(backupReason($row, $now), 'failed');
expect($row['last_capture'], $now - 100);
expect(applyBackupEvent($row, $event), null);
foreach ([array_replace($event, ['started' => $now + 301]), array_replace($event, ['snapshot' => 'bad'])] as $bad) {
    try { validateBackupEvent($bad, $now); throw new RuntimeException('Invalid event accepted'); }
    catch (InvalidArgumentException $expected) {}
}
echo "Backup freshness and event ordering checks passed\n";
