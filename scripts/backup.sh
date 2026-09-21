#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .runtime/backups
backup=".runtime/backups/postgres-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose exec -T postgres pg_dumpall -U postgres | gzip > "$backup.tmp"
mv -- "$backup.tmp" "$backup"
echo "Created $backup. Copy encrypted backups off-host; includes role password hashes."
