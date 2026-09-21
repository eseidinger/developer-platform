<?php
require __DIR__ . '/../watchdog/common.php';
$now = strtotime('2026-09-21 10:00:00 UTC');
$cases = [
    [null, false], ['2026-09-21 09:54:59', false],
    ['2026-09-21 09:55:00', true], ['2026-09-21 10:00:01', false],
];
foreach ($cases as [$time, $expected]) {
    if (heartbeatFresh($time, 300, $now) !== $expected) {
        throw new RuntimeException('Heartbeat boundary check failed');
    }
}
echo "Watchdog freshness checks passed\n";
