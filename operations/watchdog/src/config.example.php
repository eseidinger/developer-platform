<?php
// Copy to config.local.php ABOVE the public document root, never commit it.
return [
    'dsn' => 'mysql:host=localhost;dbname=watchdog;charset=utf8mb4',
    'user' => 'watchdog',
    'password' => 'replace-me',
    'token' => 'replace-with-at-least-32-random-characters',
    'max_age' => 300,
    // Optional independent backup signal. Use a DISTINCT random token (32+ chars).
    // Empty disables backup checks; enabling starts no-backup/overdue alerts.
    'backup_token' => '',
    // Optional fixed HTTPS URL, never accepted from an HTTP request.
    'health_url' => null,
    'mail_to' => 'admin@example.com',
    'mail_from' => 'watchdog@example.com',
    // Set to 'smtp' for authenticated SMTP, or 'mail' for the hosting mailer.
    'mail_transport' => 'mail',
    'smtp' => [
        'host' => 'smtp.example.com',
        'port' => 587,
        // 'starttls' (usually port 587), or 'tls' for implicit TLS (usually 465).
        'encryption' => 'starttls',
        'username' => 'watchdog@example.com',
        'password' => 'replace-with-smtp-password',
    ],
];
