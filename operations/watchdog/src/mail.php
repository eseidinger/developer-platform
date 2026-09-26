<?php
declare(strict_types=1);

function sendWatchdogMail(array $config, string $state, string $topic = 'platform', string $reason = ''): bool {
    try {
        if (!in_array($state, ['up', 'down'], true)) {
            throw new RuntimeException('Invalid watchdog state');
        }
        foreach (['mail_to', 'mail_from'] as $field) {
            if (!filter_var($config[$field] ?? '', FILTER_VALIDATE_EMAIL)
                || preg_match('/[\r\n]/', $config[$field])) {
                throw new RuntimeException('Invalid mail address');
            }
        }
        if (!in_array($topic, ['platform', 'backup'], true)
            || ($topic === 'backup' && !in_array($reason, ['up', 'failed', 'stalled', 'overdue', 'no-backup'], true))) {
            throw new RuntimeException('Invalid notification topic');
        }
        $subject = 'Developer Platform: ' . ($topic === 'backup' ? 'BACKUP ' : '') . strtoupper($state);
        $body = 'The external watchdog reports: ' . $state;
        if ($topic === 'backup') $body .= "\nBackup condition: " . $reason;
        if (($config['mail_transport'] ?? 'mail') === 'mail') {
            return mail($config['mail_to'], $subject, $body, 'From: ' . $config['mail_from']);
        }
        if ($config['mail_transport'] !== 'smtp') {
            throw new RuntimeException('Invalid mail transport');
        }
        $smtp = $config['smtp'] ?? [];
        if (!preg_match('/\A[A-Za-z0-9][A-Za-z0-9.-]*\z/', $smtp['host'] ?? '')
            || !is_int($smtp['port'] ?? null) || $smtp['port'] < 1 || $smtp['port'] > 65535
            || !in_array($smtp['encryption'] ?? '', ['starttls', 'tls'], true)
            || !is_string($smtp['username'] ?? null) || $smtp['username'] === ''
            || !is_string($smtp['password'] ?? null) || $smtp['password'] === '') {
            throw new RuntimeException('Invalid SMTP configuration');
        }
        if (!extension_loaded('curl')) {
            throw new RuntimeException('SMTP requires PHP cURL');
        }
        $message = 'Date: ' . gmdate('D, d M Y H:i:s +0000') . "\r\n"
            . 'Message-ID: <' . bin2hex(random_bytes(16)) . '@watchdog.local>' . "\r\n"
            . 'From: ' . $config['mail_from'] . "\r\n"
            . 'To: ' . $config['mail_to'] . "\r\n"
            . 'Subject: ' . $subject . "\r\n"
            . "MIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\n"
            . "Content-Transfer-Encoding: 7bit\r\n\r\n" . $body . "\r\n";
        $offset = 0;
        $scheme = $smtp['encryption'] === 'tls' ? 'smtps' : 'smtp';
        $curl = curl_init($scheme . '://' . $smtp['host'] . ':' . $smtp['port']);
        try {
            curl_setopt_array($curl, [
                CURLOPT_PROTOCOLS => CURLPROTO_SMTP | CURLPROTO_SMTPS,
                CURLOPT_USERNAME => $smtp['username'],
                CURLOPT_PASSWORD => $smtp['password'],
                CURLOPT_USE_SSL => CURLUSESSL_ALL,
                CURLOPT_SSL_VERIFYPEER => true,
                CURLOPT_SSL_VERIFYHOST => 2,
                CURLOPT_CONNECTTIMEOUT => 5,
                CURLOPT_TIMEOUT => 20,
                CURLOPT_MAIL_FROM => '<' . $config['mail_from'] . '>',
                CURLOPT_MAIL_RCPT => ['<' . $config['mail_to'] . '>'],
                CURLOPT_UPLOAD => true,
                CURLOPT_INFILESIZE => strlen($message),
                CURLOPT_READFUNCTION => static function ($handle, $stream, int $length) use ($message, &$offset): string {
                    $chunk = substr($message, $offset, $length);
                    $offset += strlen($chunk);
                    return $chunk;
                },
                CURLOPT_RETURNTRANSFER => true,
            ]);
            $success = curl_exec($curl) !== false;
            $code = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
            if (!$success || $code !== 250) {
                // Do not log server replies, credentials, or message contents.
                error_log('Watchdog SMTP delivery failed (curl=' . curl_errno($curl) . ', status=' . $code . ')');
                return false;
            }
            return true;
        } finally {
            curl_close($curl);
        }
    } catch (Throwable $error) {
        // Invalid settings and unavailable extensions also leave notifications retryable.
        error_log('Watchdog mail configuration or delivery failed');
        return false;
    }
}
