#!/usr/bin/env python3
"""Disposable real PostgreSQL catalog checks for dedicated Community resources."""
from datetime import datetime
import hashlib
import os
import secrets
import subprocess
import time
from unittest.mock import patch
from uuid import uuid4
import psycopg
from app.stores import catalog,relay
from app.stores.contract import ResourceCreate,HumanGrant,BindingRequest,GrantUpdate


def main():
    name='neo4j-catalog-'+uuid4().hex[:10]
    password=secrets.token_hex(32)
    env={**os.environ,'POSTGRES_PASSWORD':password}
    os.environ.update(DATABASE_KEY=secrets.token_hex(32),STORE_RELAY_PASSWORD=secrets.token_hex(32))
    def docker(*args):
        value=subprocess.run(['docker',*args],env=env,capture_output=True,timeout=90)
        if value.returncode:raise RuntimeError('Disposable catalog command failed')
        return value.stdout.decode().strip()
    def denied(work):
        try:work()
        except catalog.Conflict:return
        raise AssertionError('Unsupported Community capability was accepted')
    try:
        docker('run','-d','--name',name,'--memory','512m','--cpus','1','--tmpfs','/var/lib/postgresql:rw,size=256m',
            '-e','POSTGRES_PASSWORD','-e','POSTGRES_DB=platform','-p','127.0.0.1::5432','postgres:18.6-trixie')
        port=int(docker('port',name,'5432/tcp').rsplit(':',1)[1])
        def connect():return psycopg.connect(host='127.0.0.1',port=port,dbname='platform',user='postgres',password=password,autocommit=True,connect_timeout=2)
        for _ in range(100):
            try:
                with connect():break
            except psycopg.OperationalError:time.sleep(.2)
        else:raise AssertionError('Catalog database readiness failed')
        with connect() as conn:
            conn.execute('CREATE TABLE projects(name TEXT PRIMARY KEY,status TEXT)')
            conn.execute("INSERT INTO projects VALUES('alpha','applied'),('beta','applied')")
            catalog.initialize(conn);relay.initialize_identity(conn)
            def resource():return catalog.create_resource(conn,'alpha',ResourceCreate(name='graph',provider='neo4j'))
            with conn.transaction():
                catalog.lock(conn)
                first=resource()
                denied(resource)
                denied(lambda:catalog.create_human_grant(conn,first,HumanGrant(issuer='https://fixture.invalid',subject='reader',mode='read-only'),'fixture-admin'))
                human=catalog.create_human_grant(conn,first,HumanGrant(issuer='https://fixture.invalid',subject='writer',mode='read-write'),'fixture-admin')
                denied(lambda:catalog.change_mode(conn,human,GrantUpdate(version=human['version'],mode='read-only'),'fixture-admin'))
                denied(lambda:catalog.request_binding(conn,'beta',BindingRequest(resource_id=first['resource_id'],component='consumer',mode='read-only'),'fixture-admin'))
                pending=catalog.request_binding(conn,'beta',BindingRequest(resource_id=first['resource_id'],component='consumer',mode='read-write'),'fixture-admin')
                assert pending['state']=='pending'
                conn.execute("UPDATE store_resources SET observed_state='active' WHERE resource_id=%s",(first['resource_id'],))
                credential=catalog.issue(conn,human)
                assert credential['admission_sha256']==hashlib.sha256(catalog.secret_for(credential['credential_id']).encode()).hexdigest()
                assert (datetime.fromisoformat(credential['expires_at'])-datetime.fromisoformat(credential['issued_at'])).total_seconds()==86400
                conn.execute("UPDATE store_credentials SET state='active' WHERE credential_id=%s",(credential['credential_id'],))
                conn.execute('INSERT INTO store_instances(resource_id,host,port) VALUES(%s,%s,7687)',(first['resource_id'],'127.0.0.1'))
            with patch.object(relay,'connect',side_effect=connect),patch.dict(os.environ,{'STORE_ENABLED_PROVIDERS':'neo4j'}):
                snapshot=relay.snapshot()
                selected=snapshot[credential['relay_port']]
                assert selected['admission_sha256']==credential['admission_sha256'] and selected['native_host']=='127.0.0.1'
            with conn.transaction():
                catalog.retire(conn,first,first['version'])
                denied(resource)
                conn.execute("UPDATE store_resources SET state='purged' WHERE resource_id=%s",(first['resource_id'],))
                replacement=resource()
                assert replacement['resource_id']!=first['resource_id']
        print('PASS real catalog: one retained instance per project, full-access-only grants/bindings, cross-project pending approval, 24-hour verifier issuance, relay endpoint snapshot and post-purge replacement')
    finally:subprocess.run(['docker','rm','-f','-v',name],capture_output=True,timeout=30)

if __name__=='__main__':main()
