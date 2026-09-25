<?php
declare(strict_types=1);

// Database setup must never be callable through the web server.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/common.php';

$stage = 'checking PHP extensions';
$hint = 'Enable PDO-MySQL for the PHP CLI executable running this script (check php -m).';
try {
    if (!extension_loaded('pdo_mysql')) {
        throw new RuntimeException('PDO-MySQL unavailable');
    }
    $stage = 'loading configuration';
    $hint = 'Create a readable config.local.php containing valid PHP and string values for dsn, user, and password.';
    $configFile = __DIR__ . '/config.local.php';
    if (!is_file($configFile)) {
        throw new RuntimeException('Create config.local.php with database credentials first.');
    }
    // Schema setup does not depend on heartbeat or email configuration.
    $config = require $configFile;
    foreach (['dsn', 'user', 'password'] as $field) {
        if (!is_array($config) || !isset($config[$field]) || !is_string($config[$field])) {
            throw new RuntimeException('Configure dsn, user, and password in config.local.php.');
        }
    }
    if (!str_starts_with($config['dsn'], 'mysql:')) {
        throw new RuntimeException('A MySQL DSN is required');
    }
    $stage = 'reading schema.sql';
    $hint = 'Upload a readable copy of the bundled schema.sql next to this script.';
    $schema = file_get_contents(__DIR__ . '/schema.sql');
    if ($schema === false) {
        throw new RuntimeException('Cannot read schema.sql.');
    }
    $stage = 'connecting to MySQL and setting the session time zone';
    $hint = 'Check the database connection configuration and PHP PDO-MySQL installation.';
    $db = database($config);
    $statementNumber = 0;
    // The bundled schema contains simple statements, with no embedded semicolons.
    foreach (explode(';', $schema) as $statement) {
        $statement = trim($statement);
        if ($statement === '') continue;
        $stage = 'executing schema statement ' . ++$statementNumber;
        $hint = 'Check the bundled schema.sql and the database server logs.';
        try {
            $db->exec($statement);
        } catch (PDOException $error) {
            // MySQL has no portable CREATE INDEX IF NOT EXISTS syntax.
            // Ignore only the known index already existing on a repeated import.
            if (($error->errorInfo[1] ?? null) === 1061
                && $statement === 'CREATE INDEX history_time ON check_history(checked_at)') {
                continue;
            }
            throw $error;
        }
    }
    fwrite(STDOUT, "Watchdog schema imported successfully. Existing data preserved.\n");
} catch (PDOException $error) {
    // Report codes and controlled hints, never raw exception text or the DSN.
    $code = (int)($error->errorInfo[1] ?? 0);
    $sqlState = (string)($error->errorInfo[0] ?? $error->getCode());
    if (!preg_match('/\A[A-Z0-9]{5}\z/', $sqlState)) $sqlState = 'unknown';
    $hint = match ($code) {
        1044 => 'The database user cannot access this database. Check database grants and the DSN database name.',
        1045, 1698 => 'MySQL rejected authentication. Check the database username/password and which client hosts that account permits.',
        1049 => 'The configured database does not exist. Create it first or correct dbname in the DSN.',
        1142, 1143 => 'A schema operation was denied. Grant the database user CREATE, INSERT, and INDEX permissions on the watchdog database.',
        2002, 2003 => 'Cannot connect to MySQL. Check the DSN host, port or Unix socket, server availability, and network access. localhost may use a Unix socket; use the hosting provider\'s database hostname when required.',
        2005 => 'Cannot resolve the database hostname. Check the DSN host and DNS configuration.',
        default => 'Check the database server logs and schema compatibility using the error codes above.',
    };
    fwrite(STDERR, "Schema import failed while $stage (SQLSTATE=$sqlState, driver code=$code).\n$hint\n");
    exit(1);
} catch (Throwable $error) {
    fwrite(STDERR, "Schema import failed while $stage.\n$hint\n");
    exit(1);
}
