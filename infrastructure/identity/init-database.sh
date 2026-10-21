#!/bin/sh
set -e

# Wait for PostgreSQL before reconciling the dedicated identity login.
# The bootstrap runs as postgres; Keycloak itself receives only its own login.
export PGPASSWORD="$POSTGRES_PASSWORD"

until pg_isready -h postgres -U postgres -d postgres; do
  sleep 1
done

sql() {
  psql -h postgres -U postgres -d postgres "$@"
}

# Retain an existing database and refresh its login password on every run.
if ! sql -tAc "SELECT 1 FROM pg_roles WHERE rolname='keycloak'" | grep -qx 1; then
  sql -c "CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE \
NOREPLICATION PASSWORD '$KEYCLOAK_DB_PASSWORD'"
else
  sql -c "ALTER ROLE keycloak PASSWORD '$KEYCLOAK_DB_PASSWORD'"
fi

if ! sql -tAc "SELECT 1 FROM pg_database WHERE datname='keycloak'" | grep -qx 1; then
  sql -c "CREATE DATABASE keycloak OWNER keycloak"
fi
