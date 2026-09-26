CREATE TABLE IF NOT EXISTS monitor (
    id TINYINT PRIMARY KEY,
    last_heartbeat DATETIME NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'unknown',
    notified_state VARCHAR(16) NOT NULL DEFAULT 'unknown',
    checked_at DATETIME NULL
);
INSERT IGNORE INTO monitor(id) VALUES (1);
CREATE TABLE IF NOT EXISTS check_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    checked_at DATETIME NOT NULL,
    state VARCHAR(16) NOT NULL
);
CREATE INDEX history_time ON check_history(checked_at);
