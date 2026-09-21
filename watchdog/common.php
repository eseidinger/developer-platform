<?php
declare(strict_types=1);
function settings(): array {
    $file = __DIR__ . '/config.local.php';
    if (!is_file($file)) {
        throw new RuntimeException('Missing watchdog configuration');
    }
    $config = require $file;
    if (strlen($config['token'] ?? '') < 32 || str_starts_with($config['token'], 'replace-')) {
        throw new RuntimeException('Configure a random heartbeat token');
    }
    return $config;
}
function database(array $config): PDO {
    $db = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $db->exec("SET time_zone = '+00:00'");
    return $db;
}
function heartbeatFresh(?string $heartbeat, int $maxAge, int $now): bool {
    if ($heartbeat === null) return false;
    $time = strtotime($heartbeat . ' UTC');
    return $time !== false && $time <= $now && $now - $time <= $maxAge;
}
function publicFailure(Throwable $error): never {
    error_log('Watchdog failure: ' . $error->getMessage());
    http_response_code(503);
    exit('Service unavailable');
}
