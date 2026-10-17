"""Small application-owned Prometheus collector; no query text or credentials.

Mount exposition() in the application's existing authenticated /metrics route.
This library opens no listener and never exports data to an external endpoint.
"""
from contextlib import contextmanager
import json
import math
import threading
import time
from uuid import UUID

BUCKETS = (.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10,30,60,300)
OPERATIONS = {'postgresql': {'query','write','schema'}, 'pgvector': {'search','upsert','index'},
    'age': {'query','write','rebuild','validate'}, 'neo4j': {'query','write','schema'},
    'duckdb': {'query','transfer','checksum','publish'}, 's3': {'get','put'},
    'opensearch': {'search','index'}, 'qdrant': {'search','upsert'}}
PROFILE = {'cpu_seconds','peak_memory_bytes','spill_bytes','rows_scanned','rows_returned',
    'transfer_bytes','projection_lag_seconds','pending_updates','last_validation_timestamp_seconds'}


class StoreMetrics:
    def __init__(self, resource_id, provider):
        self.resource_id = str(UUID(str(resource_id)))
        if provider not in OPERATIONS: raise ValueError('Unknown store workload')
        self.provider, self.lock, self.observations, self.profiles = provider, threading.Lock(), {}, {}

    @contextmanager
    def operation(self, name):
        if name not in OPERATIONS[self.provider]: raise ValueError('Unreviewed operation')
        started, outcome = time.perf_counter(), 'success'
        try: yield
        except BaseException:
            outcome = 'error'
            raise
        finally:
            elapsed = time.perf_counter() - started
            with self.lock:
                key = name,outcome
                data = self.observations.setdefault(key, {'count':0,'seconds':0.,'buckets':[0]*len(BUCKETS)})
                data['count'] += 1
                data['seconds'] += elapsed
                for index,bound in enumerate(BUCKETS):
                    if elapsed <= bound: data['buckets'][index] += 1

    def profile(self, **values):
        if set(values) - PROFILE: raise ValueError('Unreviewed numeric field')
        if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 for v in values.values()):
            raise ValueError('Finite nonnegative numeric fields required')
        with self.lock: self.profiles.update(values)

    def duckdb_profile(self, value):
        # Never publish the query, operator tree, filenames, parameters or plans.
        keys={'cpu_time':'cpu_seconds','system_peak_buffer_memory':'peak_memory_bytes',
            'system_peak_temp_dir_size':'spill_bytes','cumulative_rows_scanned':'rows_scanned','rows_returned':'rows_returned'}
        self.profile(**{target:value[source] for source,target in keys.items() if source in value})

    def exposition(self):
        labels = {'resource_id':self.resource_id,'provider':self.provider}
        lines=[]
        def sample(name,value,extra):
            encoded=','.join(k+'='+json.dumps(str(v)) for k,v in sorted({**labels,**extra}.items()))
            lines.append('platform_store_workload_'+name+'{'+encoded+'} '+str(value))
        with self.lock:
            for (operation,outcome),data in sorted(self.observations.items()):
                dimensions={'operation':operation,'outcome':outcome}
                for bound,count in zip(BUCKETS,data['buckets']): sample('duration_seconds_bucket',count,{**dimensions,'le':str(bound)})
                sample('duration_seconds_bucket',data['count'],{**dimensions,'le':'+Inf'})
                sample('duration_seconds_sum',data['seconds'],dimensions)
                sample('duration_seconds_count',data['count'],dimensions)
            for name,value in sorted(self.profiles.items()): sample(name,value,{})
            sample('last_collection_timestamp_seconds',time.time(),{})
        return '\n'.join(lines)+'\n'
