"""Private bounded native statistics, isolated from lifecycle reconciliation.

Only reviewed numeric fields and stable catalog identities leave this process.
Failed samples retain last-good values with explicit health and freshness.
"""
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.request import Request
from . import catalog, providers


def line(name, value, labels):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Numeric metric required')
    encoded = ','.join(key + '=' + json.dumps(str(value)) for key, value in sorted(labels.items()))
    return name + '{' + encoded + '} ' + str(value)


def node_stats(value):
    definitions = {
        'jvm.mem.heap_used_in_bytes': ('heap_used_bytes', 1),
        'jvm.mem.heap_max_in_bytes': ('heap_max_bytes', 1),
        'jvm.uptime_in_millis': ('uptime_seconds', .001),
        'process.cpu.percent': ('cpu_ratio', .01),
        'process.open_file_descriptors': ('open_fds', 1),
        'fs.total.available_in_bytes': ('disk_available_bytes', 1),
        'fs.total.total_in_bytes': ('disk_total_bytes', 1),
    }
    for path, (name, scale) in definitions.items():
        current = value
        for part in path.split('.'): current = current[part]
        yield name, current * scale, {}
    for pool, stats in value.get('thread_pool', {}).items():
        if pool not in {'search', 'write', 'refresh', 'flush', 'merge', 'get'}: continue
        for field in ('active', 'queue', 'rejected', 'completed'):
            yield 'thread_pool_' + field + ('_total' if field in {'rejected', 'completed'} else ''), stats[field], {'pool': pool}
    for collector in ('young', 'old'):
        stats = value['jvm']['gc']['collectors'][collector]
        yield 'gc_seconds_total', stats['collection_time_in_millis'] / 1000, {'generation': collector}
        yield 'gc_total', stats['collection_count'], {'generation': collector}
    for name, stats in value.get('breakers', {}).items():
        if name not in {'parent', 'request', 'fielddata', 'in_flight_requests', 'accounting'}: continue
        yield 'breaker_tripped_total', stats['tripped'], {'breaker': name}


def opensearch(provider, resources):
    from .opensearch import index, authorization
    from .http_client import PrivateJSON
    root = PrivateJSON(provider.endpoint, {'Authorization': authorization('platform_monitor', os.environ['STORE_MONITOR_PASSWORD'])},
        os.environ.get('OPENSEARCH_CA_FILE'))
    nodes = root.request('GET', '/_nodes/stats/jvm,thread_pool,breaker,fs,process')['nodes']
    if len(nodes) != 1: raise ValueError('Reviewed single-node topology required')
    result = [line('platform_native_opensearch_' + name, number, {'provider': 'opensearch', 'scope': 'shared', **labels})
        for name, number, labels in node_stats(next(iter(nodes.values())))]
    health = root.request('GET', '/_cluster/health')
    result.append(line('platform_native_opensearch_health', {'green': 0, 'yellow': 1, 'red': 2}[health['status']], {'provider': 'opensearch', 'scope': 'shared'}))
    result.append(line('platform_native_opensearch_unassigned_shards', health['unassigned_shards'], {'provider': 'opensearch', 'scope': 'shared'}))
    # One bounded statistics call; ignore all indexes outside the current catalog.
    indices = root.request('GET', '/resource_*/_stats/docs,store,search,indexing,merge,query_cache,segments')['indices']
    for resource in resources:
        if resource['state'] != 'active': continue
        stats = indices[index(resource)]['primaries']
        labels = {'provider': 'opensearch', 'project': resource['owner_project'], 'resource_id': str(resource['resource_id']), 'scope': 'resource'}
        fields = {'docs.count': ('documents', 1), 'store.size_in_bytes': ('index_bytes', 1),
            'search.query_total': ('search_total', 1), 'search.query_time_in_millis': ('search_seconds_total', .001),
            'search.query_current': ('search_active', 1), 'indexing.index_total': ('index_total', 1),
            'indexing.index_time_in_millis': ('index_seconds_total', .001), 'indexing.index_failed': ('index_failed_total', 1),
            'merges.total_time_in_millis': ('merge_seconds_total', .001), 'merges.current': ('merges_active', 1),
            'query_cache.hit_count': ('cache_hits_total', 1), 'query_cache.miss_count': ('cache_misses_total', 1),
            'segments.count': ('segments', 1)}
        for path, (name, scale) in fields.items():
            first, second = path.split('.')
            result.append(line('platform_native_opensearch_' + name, stats[first][second] * scale, labels))
    return result


QDRANT = {
    'app_status_recovery_mode', 'collections_total', 'collection_points', 'collection_vectors',
    'collections_vector_total', 'collection_indexed_only_excluded_points', 'collection_active_replicas_min',
    'rest_responses_total', 'rest_responses_fail_total', 'rest_responses_duration_seconds_bucket',
    'rest_responses_duration_seconds_sum', 'rest_responses_duration_seconds_count',
    'grpc_responses_total', 'grpc_responses_fail_total', 'grpc_responses_duration_seconds_bucket',
    'grpc_responses_duration_seconds_sum', 'grpc_responses_duration_seconds_count',
    'memory_active_bytes', 'memory_allocated_bytes', 'memory_resident_bytes',
    'process_threads', 'process_open_fds', 'process_max_fds', 'process_major_page_faults_total',
    'process_minor_page_faults_total', 'collection_running_optimizations', 'snapshot_creation_running', 'snapshot_recovery_running', 'snapshot_created_total',
}
SAMPLE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})? ([+\-0-9.eE]+)(?: [0-9]+)?$')
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z_0-9]*)="((?:[^"\\]|\\[\\"n])*)"(?:,|$)')


def qdrant_samples(raw, resources):
    if len(raw) > 2 * 1024 * 1024: raise ValueError('Metrics response limit')
    known = {catalog.identifier(r['resource_id']): r for r in resources}
    result = []
    for item in raw.splitlines():
        if not item or item.startswith('#'): continue
        candidate = re.split(r'[ {]', item, maxsplit=1)[0]
        if candidate not in QDRANT: continue
        matched = SAMPLE.fullmatch(item)
        if not matched: raise ValueError('Unsupported metric format')
        name, encoded, number = matched.groups()
        if name not in QDRANT: continue
        labels = {}
        position = 0
        for pair in LABEL.finditer(encoded or ''):
            if pair.start() != position or pair[1] in labels: raise ValueError('Invalid labels')
            labels[pair[1]] = json.loads('"' + pair[2] + '"')
            position = pair.end()
        if position != len(encoded or ''): raise ValueError('Invalid labels')
        if len(labels) > 10 or any(len(v) > 256 for v in labels.values()): raise ValueError('Label limit')
        if name.startswith('collection_') and 'id' in labels:
            labels['collection'] = labels.pop('id')
        for vector_label in ('vector','vector_name'):
            if labels.get(vector_label) == '': del labels[vector_label]
        selected = {'provider': 'qdrant', 'scope': 'shared'}
        if 'collection' in labels:
            resource = known.get(labels['collection'])
            if resource is None: continue
            selected.update(project=resource['owner_project'], resource_id=str(resource['resource_id']), scope='resource')
        # Endpoint is a native reviewed template, never a resolved URL.
        if 'endpoint' in labels:
            endpoint = labels['endpoint']
            if not re.fullmatch(r'(?:/[a-z_/{}/]+|qdrant\.[A-Za-z]+/[A-Za-z]+)', endpoint): continue
            selected['operation'] = endpoint
        for key in ('method', 'status', 'le'):
            if key in labels:
                if key == 'method' and labels[key] not in {'GET','POST','PUT','DELETE','PATCH'}: continue
                if key == 'status' and not re.fullmatch('[0-9]{1,3}', labels[key]): continue
                selected[key] = labels[key]
        # Different vector-name label sets must not collapse into duplicate series.
        if set(labels) - {'collection', 'endpoint', 'method', 'status', 'le'}: continue
        result.append(line('platform_native_qdrant_' + name, float(number), selected))
        if len(result) > 5000: raise ValueError('Metric series limit')
    if not result: raise ValueError('No supported metrics')
    return result


def qdrant(provider, resources):
    request = Request(provider.endpoint + '/metrics?per_collection=true',
        headers={'api-key': os.environ['STORE_MONITOR_PASSWORD']})
    with provider.root.opener.open(request, timeout=5) as response:
        raw = response.read(2 * 1024 * 1024 + 1).decode('utf-8')
    return qdrant_samples(raw, resources)


def containers(resources):
    from .neo4j import Neo4j
    root = Neo4j().call('containers', {'resource_id': '00000000-0000-0000-0000-000000000000'})
    known = {str(r['resource_id']): r for r in resources}
    result = []
    for item in root['containers']:
        provider = item['provider']
        if provider not in {'postgresql','s3','qdrant','opensearch','neo4j'}: raise ValueError()
        labels = {'provider': provider, 'scope': 'shared'}
        if item.get('resource_id'):
            resource = known.get(item['resource_id'])
            if resource is None: continue
            labels.update(project=resource['owner_project'], resource_id=str(resource['resource_id']), scope='resource')
        for key in ('running','restarts','cpu_seconds_total','memory_bytes','memory_limit_bytes','cpu_limit_cores','read_bytes_total','write_bytes_total'):
            if key in item: result.append(line('platform_native_container_' + key, item[key], labels))
    return result


def neo4j(provider,resources):
    result=[]
    for resource in resources:
        if resource['state']!='active':continue
        labels={'provider':'neo4j','project':resource['owner_project'],'resource_id':str(resource['resource_id']),'scope':'resource'}
        for name,value in provider.call('jvm',resource).items():
            if name not in {'platform_jvm_heap_used_bytes','platform_jvm_heap_max_bytes','platform_jvm_heap_committed_bytes','platform_jvm_gc_seconds_total','platform_jvm_threads'}:raise ValueError()
            result.append(line(name.replace('platform_jvm_','platform_native_neo4j_jvm_'),value,labels))
    return result


PG_CACHE = {}
PG_OFFSET = 0


def postgres(provider, resources):
    import psycopg
    global PG_OFFSET
    active = [r for r in resources if r['state'] == 'active']
    known = {str(r['resource_id']) for r in active}
    for rid in list(PG_CACHE):
        if rid not in known: del PG_CACHE[rid]
    chosen = (active[PG_OFFSET:] + active[:PG_OFFSET])[:8]
    PG_OFFSET = (PG_OFFSET + 8) % max(1, len(active))
    for resource in chosen:
        labels = {'provider': 'postgresql', 'project': resource['owner_project'], 'resource_id': str(resource['resource_id']), 'scope': 'resource'}
        try:
            with psycopg.connect(host=os.environ['POSTGRES_HOST'], dbname=catalog.identifier(resource['resource_id']),
                    user='platform_monitor', password=os.environ['POSTGRES_MONITOR_PASSWORD'], connect_timeout=2,
                    options='-c statement_timeout=2000 -c default_transaction_read_only=on', autocommit=True) as conn:
                row = conn.execute("""SELECT coalesce(sum(n_live_tup),0),coalesce(sum(n_dead_tup),0),
                    coalesce(sum(vacuum_count+autovacuum_count),0),coalesce(sum(analyze_count+autoanalyze_count),0)
                    FROM pg_stat_user_tables""").fetchone()
                readings = [line('platform_native_postgresql_' + name, float(value), labels) for name, value in zip(
                    ('estimated_live_rows','estimated_dead_rows','vacuums_total','analyzes_total'), row)]
                indexes = conn.execute("""SELECT a.amname,coalesce(sum(s.idx_scan),0),coalesce(sum(pg_relation_size(s.indexrelid)),0)
                    FROM pg_stat_user_indexes s JOIN pg_class c ON c.oid=s.indexrelid JOIN pg_am a ON a.oid=c.relam
                    WHERE a.amname IN ('hnsw','ivfflat') GROUP BY a.amname""").fetchall()
                for kind, scans, size in indexes:
                    readings.extend([line('platform_native_pgvector_index_scans_total', float(scans), {**labels,'index_type':kind}),
                        line('platform_native_pgvector_index_bytes', float(size), {**labels,'index_type':kind})])
                progress = conn.execute("""SELECT count(*),coalesce(sum(blocks_done),0),coalesce(sum(blocks_total),0)
                    FROM pg_stat_progress_create_index WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database())""").fetchone()
                readings.extend(line('platform_native_postgresql_index_build_' + name, float(value), labels)
                    for name,value in zip(('active','blocks_done','blocks_total'), progress))
            readings.append(line('platform_native_resource_last_success_timestamp_seconds', time.time(), labels))
            PG_CACHE[str(resource['resource_id'])] = readings
        except Exception:
            # Keep old samples with their own original success time.
            pass
    return [item for readings in PG_CACHE.values() for item in readings]


def loop(stop, control):
    from ..monitoring import atomic_write
    cache = {}
    while not stop.is_set():
        try:
            with control.connect() as conn:
                resources = [row[0] for row in conn.execute("SELECT row_to_json(r) FROM store_resources r WHERE state<>'purged' ORDER BY resource_id LIMIT 128").fetchall()]
            selected = set(os.environ.get('STORE_ENABLED_PROVIDERS', '').split(','))
            now, lines = time.time(), []
            for native in ('s3',):
                lines.append(line('platform_native_selected', int(native in selected), {'provider':native}))
            for name, collect in [('postgresql', postgres), ('opensearch', opensearch), ('qdrant', qdrant), ('neo4j', neo4j)]:
                enabled = name == 'postgresql' or name in selected
                lines.append(line('platform_native_selected', int(enabled), {'provider': name}))
                if not enabled:
                    cache.pop(name, None)
                    continue
                up = 0
                try:
                    readings = collect(providers.get(name), [r for r in resources if r['provider'] == name])
                    cache[name] = (now, readings)
                    up = 1
                except Exception:
                    pass  # Native diagnostics can contain secrets/data.
                stamp, readings = cache.get(name, (0, []))
                lines.extend(readings)
                lines.append(line('platform_native_collection_up', up, {'provider': name}))
                lines.append(line('platform_native_last_success_timestamp_seconds', stamp, {'provider': name}))
            try:
                readings = containers(resources)
                cache['containers'] = (time.time(), readings)
                container_up = 1
            except Exception:
                container_up = 0
            stamp, readings = cache.get('containers', (0, []))
            lines.extend(readings)
            lines.append(line('platform_native_collection_up', container_up, {'provider': 'containers'}))
            lines.append(line('platform_native_last_success_timestamp_seconds', stamp, {'provider': 'containers'}))
            lines.append(line('platform_native_collector_timestamp_seconds', time.time(), {}))
            root = Path(os.environ.get('MONITORING_DISCOVERY_DIR', '/var/lib/platform-monitoring'))
            atomic_write(root / 'stores-native.prom', '\n'.join(lines) + '\n')
        except Exception:
            pass  # Leave the previous heartbeat to become visibly stale.
        stop.wait(30)
