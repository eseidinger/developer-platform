#!/usr/bin/env python3
"""Disposable native RustFS -> production Alloy -> Prometheus/dashboard fixture."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.parse
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[4]

def run(*args,env=None,timeout=40):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env=env)
    if r.returncode: raise RuntimeError('Disposable native metric fixture command failed')
    return r.stdout.strip()


def main():
    suffix=uuid4().hex[:10]
    prom,alloy,store=['store-metrics-'+suffix+'-'+name for name in ('prom','alloy','rustfs')]
    env={**os.environ,'RUSTFS_ACCESS_KEY':secrets.token_hex(10),'RUSTFS_SECRET_KEY':secrets.token_hex(32)}
    with tempfile.TemporaryDirectory(prefix='store-metric-pipeline-') as directory:
        tmp=Path(directory);tmp.chmod(0o755)
        (tmp/'prom.yml').write_text('global:\n  scrape_interval: 5s\nscrape_configs: []\n')
        source=(ROOT/'infrastructure/monitoring/config.alloy').read_text()
        (tmp/'config.alloy').write_text(source[source.index('// Pinned RustFS emits'):].replace('http://prometheus:9090/api/v1/otlp','http://127.0.0.1:9090/api/v1/otlp'))
        def wait(callback,seconds=45):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                try:
                    value=callback()
                    if value:return value
                except Exception:pass
                time.sleep(.5)
            raise AssertionError('Disposable metric fixture readiness failed')
        def query(expression):
            raw=run('docker','exec',prom,'wget','-T','3','-qO-', 'http://127.0.0.1:9090/api/v1/query?query='+urllib.parse.quote(expression))
            value=json.loads(raw)
            if value['status']!='success':raise AssertionError('Invalid dashboard PromQL')
            return value['data']['result']
        try:
            run('docker','run','-d','--name',prom,'--network','none','--memory','256m','-v',f'{tmp}/prom.yml:/etc/prometheus/prometheus.yml:ro','prom/prometheus:v3.14.0','--config.file=/etc/prometheus/prometheus.yml','--web.enable-otlp-receiver')
            run('docker','run','-d','--name',alloy,'--network','container:'+prom,'--memory','512m','-v',f'{tmp}/config.alloy:/etc/alloy/config.alloy:ro','grafana/alloy:v1.19.2','run','/etc/alloy/config.alloy')
            wait(lambda: 'running' in run('docker','inspect',alloy,'--format','{{.State.Status}}'))
            run('docker','run','-d','--name',store,'--network','container:'+prom,'--memory','768m','--cpus','1',
                '--tmpfs','/data:rw,uid=10001,gid=10001,size=64m','--tmpfs','/logs:rw,uid=10001,gid=10001,size=16m',
                '-e','RUSTFS_ACCESS_KEY','-e','RUSTFS_SECRET_KEY','-e','RUSTFS_OBS_LOG_DIRECTORY=/logs',
                '-e','RUSTFS_OBS_METRIC_ENDPOINT=http://127.0.0.1:4320/v1/metrics','-e','RUSTFS_OBS_METER_INTERVAL=2',
                '-e','RUSTFS_OBS_TRACES_EXPORT_ENABLED=false','-e','RUSTFS_OBS_LOGS_EXPORT_ENABLED=false',
                'rustfs/rustfs:1.0.2@sha256:7e948dad4748bda48f8985fda7195f8cf2e4259427011f6120acc2c9acf51587',env=env)
            wait(lambda: run('docker','exec',store,'wget','-q','-O','-','http://127.0.0.1:9000/health/ready') is not None)
            # Application container performs signed native I/O; no host-published store/collector port.
            code="""import os,boto3
from botocore.config import Config
c=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id=os.environ['RUSTFS_ACCESS_KEY'],aws_secret_access_key=os.environ['RUSTFS_SECRET_KEY'],region_name='us-east-1',config=Config(s3={'addressing_style':'path'}))
c.create_bucket(Bucket='fixture-metrics')
for _ in range(8):
 c.put_object(Bucket='fixture-metrics',Key='private-fixture-marker',Body=b'synthetic')
 c.get_object(Bucket='fixture-metrics',Key='private-fixture-marker')['Body'].close()
"""
            run('docker','run','--rm','--network','container:'+prom,'--memory','256m','--entrypoint','python','-e','RUSTFS_ACCESS_KEY','-e','RUSTFS_SECRET_KEY','developer-platform-api:phase7-review','-c',code,env=env)
            observed=wait(lambda:query('rustfs_http_server_requests_total{provider="s3"}'))
            assert sum(float(row['value'][1]) for row in observed)>0
            metrics=query('{__name__=~"rustfs_.*"}')
            assert metrics and 'private-fixture-marker' not in json.dumps(metrics)
            assert all(set(row['metric'])<={'__name__','instance','job','provider','scope','operation','method','status','status_code','api','http_request_method','http_response_status_code','le'} for row in metrics)
            assert query('rustfs_http_server_request_duration_seconds_bucket{provider="s3"}')
            print('PASS native signed RustFS I/O -> production Alloy allowlist/aggregation -> Prometheus histogram/counters; object keys and sensitive dimensions excluded')
            # All provisioned store queries parse against the actual pinned engine.
            names={'postgresql','named-data-stores','rustfs-s3','opensearch-performance','qdrant-performance','neo4j-community','age-performance','pgvector-performance','duckdb-parquet'}
            count=0
            for path in (ROOT/'infrastructure/monitoring/dashboards').glob('*.json'):
                if path.stem not in names:continue
                for panel in json.loads(path.read_text())['panels']:
                    for target in panel.get('targets',[]):
                        expression=target['expr'].replace('$project','.*').replace('$resource','.*').replace('$database','platform')
                        query(expression);count+=1
            print('PASS',count,'store dashboard PromQL expressions parsed by pinned Prometheus')
        finally:
            for name in (store,alloy,prom):subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)

if __name__=='__main__':main()
