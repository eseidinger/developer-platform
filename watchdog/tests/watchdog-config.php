<?php
return [
    'dsn' => 'mysql:host=mysql;dbname=watchdog;charset=utf8mb4',
    'user' => 'watchdog',
    'password' => getenv('TEST_PASSWORD'),
    'token' => getenv('TEST_TOKEN'),
    'max_age' => 300,
    'health_url' => null,
    'mail_to' => 'test@example.com',
    'mail_from' => 'watchdog@example.com',
];
