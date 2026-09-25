<?php
declare(strict_types=1);
require __DIR__ . '/../watchdog/mail.php';

function check(bool $ok, string $message): void {
    if (!$ok) throw new RuntimeException($message);
}

// A disposable SMTP server; no email leaves this process.
if (($argv[1] ?? '') === '--server') {
    $mode = $argv[4];
    $context = stream_context_create(['ssl' => ['local_cert' => $argv[2], 'local_pk' => $argv[3]]]);
    $server = stream_socket_server('tcp://127.0.0.1:0', $errno, $error, STREAM_SERVER_BIND | STREAM_SERVER_LISTEN, $context);
    check($server !== false, 'Cannot start SMTP fixture');
    echo substr(strrchr(stream_socket_get_name($server, false), ':'), 1) . "\n";
    flush();
    $client = stream_socket_accept($server, 10);
    check($client !== false, 'No SMTP connection');
    stream_set_timeout($client, 5);
    $secure = false;
    if ($mode === 'tls' || $mode === 'bad-cert') {
        $secure = @stream_socket_enable_crypto($client, true, STREAM_CRYPTO_METHOD_TLS_SERVER) === true;
        if ($mode === 'bad-cert') { fclose($client); exit(0); }
        check($secure, 'Implicit TLS failed');
    }
    fwrite($client, "220 localhost test SMTP\r\n");
    $authenticated = false;
    while (($line = fgets($client)) !== false) {
        $line = rtrim($line, "\r\n");
        if (str_starts_with($line, 'EHLO ')) {
            fwrite($client, $secure ? "250-localhost\r\n250 AUTH PLAIN\r\n" : ($mode === 'no-tls' ? "250 localhost\r\n" : "250-localhost\r\n250 STARTTLS\r\n"));
        } elseif ($line === 'STARTTLS') {
            fwrite($client, "220 Start TLS\r\n");
            $secure = stream_socket_enable_crypto($client, true, STREAM_CRYPTO_METHOD_TLS_SERVER) === true;
            check($secure, 'STARTTLS failed');
        } elseif (str_starts_with($line, 'AUTH PLAIN')) {
            check($secure, 'Credentials sent without TLS');
            $encoded = substr($line, 11);
            if ($encoded === '') {
                fwrite($client, "334 \r\n");
                $encoded = trim(fgets($client));
            }
            check(base64_decode($encoded) === "\0smtp-user\0smtp-password", 'Wrong credentials');
            $authenticated = $mode !== 'auth-fail';
            fwrite($client, $authenticated ? "235 Authenticated\r\n" : "535 Authentication failed\r\n");
        } elseif (str_starts_with($line, 'MAIL FROM:')) {
            check($authenticated && $line === 'MAIL FROM:<watchdog@example.com>', 'Wrong sender or missing auth');
            fwrite($client, "250 OK\r\n");
        } elseif (str_starts_with($line, 'RCPT TO:')) {
            check($line === 'RCPT TO:<admin@example.com>', 'Wrong recipient');
            fwrite($client, $mode === 'recipient-fail' ? "550 Rejected\r\n" : "250 OK\r\n");
        } elseif ($line === 'DATA') {
            fwrite($client, "354 Send message\r\n");
            $message = '';
            while (($part = fgets($client)) !== false && $part !== ".\r\n") $message .= $part;
            check(str_contains($message, "Subject: Developer Platform: DOWN\r\n"), 'Wrong subject');
            check(str_contains($message, 'The external watchdog reports: down'), 'Wrong body');
            fwrite($client, $mode === 'data-fail' ? "554 Rejected\r\n" : "250 Queued\r\n");
        } elseif ($line === 'QUIT') {
            fwrite($client, "221 Bye\r\n");
            break;
        } else {
            throw new RuntimeException('Unexpected SMTP command');
        }
    }
    fclose($client);
    fclose($server);
    exit(0);
}

$certFile = ini_get('curl.cainfo');
check($certFile !== '' && !file_exists($certFile), 'Set curl.cainfo to an unused temporary certificate path');
$keyFile = $certFile . '.key';
check(!file_exists($keyFile), 'Temporary key path already exists');
umask(0077);
$key = openssl_pkey_new(['private_key_bits' => 2048]);
$csr = openssl_csr_new(['commonName' => 'localhost'], $key);
$cert = openssl_csr_sign($csr, null, $key, 1);
openssl_x509_export_to_file($cert, $certFile);
openssl_pkey_export_to_file($key, $keyFile);
$config = [
    'mail_transport' => 'smtp', 'mail_from' => 'watchdog@example.com', 'mail_to' => 'admin@example.com',
    'smtp' => ['host' => 'localhost', 'port' => 587, 'encryption' => 'starttls', 'username' => 'smtp-user', 'password' => 'smtp-password'],
];
try {
    foreach (['starttls', 'tls', 'auth-fail', 'recipient-fail', 'data-fail', 'no-tls', 'bad-cert'] as $mode) {
        $process = proc_open([PHP_BINARY, __FILE__, '--server', $certFile, $keyFile, $mode], [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        fclose($pipes[0]);
        $config['smtp']['port'] = (int)fgets($pipes[1]);
        $config['smtp']['host'] = $mode === 'bad-cert' ? '127.0.0.1' : 'localhost';
        $config['smtp']['encryption'] = in_array($mode, ['tls', 'bad-cert'], true) ? 'tls' : 'starttls';
        $sent = sendWatchdogMail($config, 'down');
        $errors = stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        check(proc_close($process) === 0, 'SMTP fixture failed: ' . $errors);
        check($sent === in_array($mode, ['starttls', 'tls'], true), 'Unexpected delivery result: ' . $mode);
        echo "PASS: $mode\n";
    }
    $config['mail_to'] = "admin@example.com\r\nBcc: other@example.com";
    check(!sendWatchdogMail($config, 'down'), 'Header injection accepted');
    $config['mail_to'] = 'admin@example.com';
    $config['smtp']['encryption'] = 'none';
    check(!sendWatchdogMail($config, 'down'), 'Plaintext SMTP accepted');
    $config['mail_transport'] = 'unknown';
    check(!sendWatchdogMail($config, 'down'), 'Unknown transport accepted');
    unset($config['mail_transport']);
    check(sendWatchdogMail($config, 'up'), 'Legacy mail transport failed');
    echo "PASS: validation and legacy mail transport\n";
} finally {
    unlink($certFile);
    unlink($keyFile);
}
