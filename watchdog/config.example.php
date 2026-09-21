<?php
// Copy to config.local.php ABOVE the public document root, never commit it.
return [
    'dsn' => 'mysql:host=localhost;dbname=watchdog;charset=utf8mb4',
    'user' => 'watchdog',
    'password' => 'replace-me',
    'token' => 'replace-with-at-least-32-random-characters',
    'max_age' => 300,
    // Optional fixed HTTPS URL, never accepted from an HTTP request.
    'health_url' => null,
    'mail_to' => 'admin@example.com',
    'mail_from' => 'watchdog@example.com',
];
