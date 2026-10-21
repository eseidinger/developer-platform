#!/bin/bash
set -euo pipefail

start_server() {
  local options="-k /tmp -h '' -c shared_preload_libraries=$1"
  options+=" -c timescaledb.telemetry_level=off -c max_worker_processes=16"
  pg_ctl -D /tmp/compat-data -l /tmp/server.log -o "$options" \
    -w start >/dev/null
}

sql() {
  psql -X -v ON_ERROR_STOP=1 "$@"
}

graph_query() {
  sql -At -U compat_app -d "$1" <<'SQL'
SET search_path=ag_catalog,public;
SELECT * FROM cypher(
  'compat_graph', $$ MATCH (n:Node) RETURN count(n) $$
) AS (value agtype);
SQL
}

# The OID workaround is confined to fixture databases, never application data.
repair_age_fixture() {
  sql -d "$1" <<'SQL' >/dev/null
BEGIN;
ALTER TABLE ag_catalog.ag_label DROP CONSTRAINT fk_graph_oid;
UPDATE ag_catalog.ag_label l
SET graph=g.namespace::oid
FROM ag_catalog.ag_graph g
WHERE l.graph=g.graphid AND g.graphid IS DISTINCT FROM g.namespace::oid;
UPDATE ag_catalog.ag_graph SET graphid=namespace::oid
WHERE graphid IS DISTINCT FROM namespace::oid;
ALTER TABLE ag_catalog.ag_label ADD CONSTRAINT fk_graph_oid
FOREIGN KEY(graph) REFERENCES ag_catalog.ag_graph(graphid);
COMMIT;
SQL
}

# Exercise every extension subset in both creation orders.
check_extension_combinations() {
  local order mask db extension index opposite saved
  local -a extensions
  for order in forward reverse; do
    for mask in 0 1 2 3 4 5 6 7; do
      db="compat_${order}_${mask}"
      createdb --owner=compat_app "$db"
      extensions=()
      if (( mask & 1 )); then
        extensions+=(vector)
      fi
      if (( mask & 2 )); then
        extensions+=(age)
      fi
      if (( mask & 4 )); then
        extensions+=(timescaledb)
      fi
      if [[ "$order" == reverse ]]; then
        # Reverse in place, including the empty subset, without word splitting.
        for ((index = 0; index < ${#extensions[@]} / 2; index++)); do
          opposite=$((${#extensions[@]} - index - 1))
          saved=${extensions[index]}
          extensions[index]=${extensions[opposite]}
          extensions[opposite]=$saved
        done
      fi
      for extension in "${extensions[@]}"; do
        sql -d "$db" -c "CREATE EXTENSION $extension;" >/dev/null
      done
      sql -U compat_app -d "$db" -c "
        CREATE TABLE ordinary_data (id int PRIMARY KEY, value text);
        INSERT INTO ordinary_data VALUES (1, 'retained');
      " >/dev/null
      if (( mask & 1 )); then
        sql -U compat_app -d "$db" -c "
          CREATE TABLE embeddings(id int, embedding public.vector(3));
          INSERT INTO embeddings VALUES(1,'[1,2,3]'),(2,'[4,5,6]');
          CREATE INDEX ON embeddings USING hnsw (embedding public.vector_l2_ops);
          SELECT id FROM embeddings
          ORDER BY embedding <-> '[1,2,3]'::public.vector LIMIT 1;
        " >/dev/null
      fi
      if (( mask & 2 )); then
        sql -d "$db" -c "GRANT USAGE ON SCHEMA ag_catalog TO compat_app;" >/dev/null
        sql -U compat_app -d "$db" <<'SQL' >/dev/null
SET search_path=ag_catalog,public;
SELECT create_graph('compat_graph');
SELECT * FROM cypher(
  'compat_graph', $$ CREATE (:Node {id: 1})-[:LINK]->(:Node {id: 2}) $$
) AS (value agtype);
SELECT * FROM cypher(
  'compat_graph', $$ MATCH (a:Node)-[:LINK]->(b:Node) RETURN a.id,b.id $$
) AS (a agtype,b agtype);
SQL
      fi
      if (( mask & 4 )); then
        sql -U compat_app -d "$db" -c "
          CREATE TABLE measurements(
            time timestamptz NOT NULL, value double precision
          );
          SELECT create_hypertable('measurements',by_range('time'));
          INSERT INTO measurements VALUES(now(),42);
          SELECT time_bucket('1 hour',time),avg(value)
          FROM measurements GROUP BY 1;
        " >/dev/null
      fi
      sql -At -d "$db" \
        -c 'SELECT extname,extversion FROM pg_extension ORDER BY extname;' \
        | tr '\n' ' '
      printf ' PASS database=%s role=compat_app\n' "$db"
    done
  done
}

# Preloading must not enable extensions in ordinary resource databases.
check_plain_database() {
  local extension_count
  extension_count=$(sql -At -d compat_forward_0 -c "
    SELECT count(*) FROM pg_extension
    WHERE extname IN ('age','vector','timescaledb');
  ")
  [[ "$extension_count" == 0 ]]
  printf 'PASS plain database has no optional extensions\n'
}

# A server restart must preserve all three extension query types.
check_reversed_preload() {
  pg_ctl -D /tmp/compat-data -m fast -w stop >/dev/null
  start_server age,timescaledb
  sql -U compat_app -d compat_forward_7 <<'SQL' >/dev/null
SET search_path=ag_catalog,public;
SELECT * FROM cypher(
  'compat_graph', $$ MATCH (n:Node) RETURN count(n) $$
) AS (value agtype);
SELECT id FROM embeddings ORDER BY embedding <-> '[1,2,3]'::public.vector LIMIT 1;
SELECT time_bucket('1 hour',time),avg(value) FROM measurements GROUP BY 1;
SQL
  printf 'PASS reversed shared_preload_libraries and persisted data after restart\n'
}

# Restore vector/time-series data using the required Timescale restore hooks.
check_combined_restore() {
  pg_dump -Fc compat_forward_7 > /tmp/all.dump
  createdb --owner=compat_app compat_restored
  sql -d compat_restored -c 'CREATE EXTENSION timescaledb;' >/dev/null
  sql -d compat_restored -c 'SELECT timescaledb_pre_restore();' >/dev/null
  pg_restore -d compat_restored --exit-on-error /tmp/all.dump
  sql -d compat_restored -c 'SELECT timescaledb_post_restore();' >/dev/null
  # Vector and time-series operations must survive the same combined restore.
  sql -U compat_app -d compat_restored -c "
    SELECT id FROM embeddings
    ORDER BY embedding <-> '[1,2,3]'::public.vector LIMIT 1;
    SELECT time_bucket('1 hour',time),avg(value) FROM measurements GROUP BY 1;
  " >/dev/null
  printf 'PASS vector and time-series queries after combined logical restore\n'
}

# Record the known AGE limitation; repair only these disposable fixtures.
check_age_restore() {
  local variant restored
  for variant in combined age_only; do
    restored=compat_restored
    if [[ "$variant" == age_only ]]; then
      pg_dump -Fc compat_forward_2 > /tmp/age.dump
      createdb --owner=compat_app compat_age_restored
      pg_restore -d compat_age_restored --exit-on-error /tmp/age.dump
      restored=compat_age_restored
    fi
    if graph_query "$restored" > /tmp/graph.out 2>&1; then
      printf 'PASS unmodified AGE %s logical restore\n' "$variant"
    else
      if ! grep -q 'graph with oid .* does not exist' /tmp/graph.out; then
        cat /tmp/graph.out
        exit 1
      fi
      printf 'LIMITATION AGE %s logical restore: ' "$variant"
      cat /tmp/graph.out
      sql -At -d "$restored" -c '
        SELECT name,graphid,namespace::oid,graphid=namespace::oid AS healthy
        FROM ag_catalog.ag_graph;
      '

      # Test the reported upstream workaround only on these disposable fixtures.
      # This is evidence, not an automatic repair of real application databases.
      repair_age_fixture "$restored"
      [[ "$(graph_query "$restored" | tail -1)" == 2 ]]
      printf 'PASS AGE %s query after fixture-only OID repair\n' "$variant"
    fi
  done
}

# Verify the restricted-role result when AGE is not globally preloaded.
check_session_loading() {
  pg_ctl -D /tmp/compat-data -m fast -w stop >/dev/null
  start_server timescaledb
  if sql -U compat_app -d compat_forward_3 -c "LOAD 'age';" >/tmp/load.out 2>&1; then
    printf 'PASS AGE non-superuser LOAD without global preload\n'
  else
    if ! grep -q 'access to library "age" is not allowed' /tmp/load.out; then
      cat /tmp/load.out
      exit 1
    fi
    printf 'LIMITATION AGE non-superuser LOAD without global preload: '

    cat /tmp/load.out
  fi
}

# Include the exact reviewed revisions in the evidence output.
report_commits() {
  printf 'COMMITS\n'
  local component
  for component in vector age timescale; do
    printf '%s ' "$component"
    git -c safe.directory=/build/"$component" -C /build/"$component" rev-parse HEAD
  done
}

# This harness runs only against temporary databases inside the build fixture.
export PGHOST=/tmp PGUSER=postgres
initdb -D /tmp/compat-data --auth=trust --no-locale > /tmp/init.log
trap 'pg_ctl -D /tmp/compat-data -m immediate stop >/dev/null 2>&1 || true' EXIT

start_server timescaledb,age
sql -At -c "
  SELECT version();
  SELECT name,default_version FROM pg_available_extensions
  WHERE name IN ('vector','age','timescaledb') ORDER BY name;
"
sql -c "CREATE ROLE compat_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;" >/dev/null

check_extension_combinations
check_plain_database
check_reversed_preload
check_combined_restore
check_age_restore
check_session_loading
report_commits
