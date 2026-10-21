#!/usr/bin/env python3
"""Disposable bound-application check for artifact metadata and search projection.

Run only in a short-lived pod with SOURCE_, ARTIFACT_ and SEARCH_ managed
binding variables. The project and all three resources must be disposable.
"""
import base64
import hashlib
import json
import os
from uuid import uuid4

import boto3
from botocore.config import Config
import httpx
import psycopg
from psycopg.types.json import Jsonb


def require(name):
    return os.environ[name]


def main():
    parquet = base64.b64decode(require('FIXTURE_PARQUET_B64'), validate=True)
    assert parquet.startswith(b'PAR1') and parquet.endswith(b'PAR1')
    s3 = boto3.client('s3', endpoint_url=require('ARTIFACT_AWS_ENDPOINT_URL_S3'),
        aws_access_key_id=require('ARTIFACT_AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=require('ARTIFACT_AWS_SECRET_ACCESS_KEY'),
        region_name=require('ARTIFACT_AWS_DEFAULT_REGION'),
        config=Config(s3={'addressing_style': 'path'}, retries={'max_attempts': 2},
            request_checksum_calculation='when_required', response_checksum_validation='when_required'))
    bucket = require('ARTIFACT_S3_BUCKET')
    prefix = 'phase7-flow/' + uuid4().hex + '/'
    data_key = prefix + 'data.parquet'
    checksum = hashlib.sha256(parquet).hexdigest()
    data_version = s3.put_object(Bucket=bucket, Key=data_key, Body=parquet)['VersionId']
    reference = {'key': data_key, 'version': data_version, 'bytes': len(parquet), 'sha256': checksum}
    manifest = json.dumps(reference, sort_keys=True, separators=(',', ':')).encode()
    manifest_key = prefix + 'manifest.json'
    manifest_version = s3.put_object(Bucket=bucket, Key=manifest_key, Body=manifest)['VersionId']
    assert manifest_version and data_version and manifest_version != 'null' and data_version != 'null'
    s3.put_object(Bucket=bucket, Key=data_key, Body=b'newer version')
    read = s3.get_object(Bucket=bucket, Key=data_key, VersionId=data_version)['Body'].read()
    assert len(read) == reference['bytes'] and hashlib.sha256(read).hexdigest() == checksum
    assert json.loads(s3.get_object(Bucket=bucket, Key=manifest_key,
        VersionId=manifest_version)['Body'].read()) == reference

    conn = psycopg.connect(host=require('SOURCE_PGHOST'), port=int(require('SOURCE_PGPORT')),
        dbname=require('SOURCE_PGDATABASE'), user=require('SOURCE_PGUSER'),
        password=require('SOURCE_PGPASSWORD'), sslmode='disable', connect_timeout=10,
        autocommit=True)
    search = httpx.Client(base_url=require('SEARCH_OPENSEARCH_URL'),
        auth=(require('SEARCH_OPENSEARCH_USERNAME'), require('SEARCH_OPENSEARCH_PASSWORD')),
        timeout=15, trust_env=False)
    index = require('SEARCH_OPENSEARCH_INDEX')
    doc_id = 'dataset-' + uuid4().hex

    def source():
        return conn.execute('SELECT title, version, deleted FROM phase7_flow.documents WHERE id=%s',
            (doc_id,)).fetchone()

    def project():
        pending = conn.execute('SELECT event_id, version FROM phase7_flow.outbox '
            'WHERE doc_id=%s AND NOT processed ORDER BY event_id', (doc_id,)).fetchall()
        for event_id, version in pending:
            title, current, deleted = source()
            assert current >= version
            path = '/' + index + '/_doc/' + doc_id + '?refresh=true'
            response = (search.delete(path) if deleted else search.put(path,
                json={'title': title, 'version': current, 'artifact': manifest_key}))
            assert response.status_code in ({200, 404} if deleted else {200, 201})
            conn.execute('UPDATE phase7_flow.outbox SET processed=true WHERE event_id=%s', (event_id,))

    try:
        with conn.transaction():
            conn.execute('CREATE SCHEMA phase7_flow')
            conn.execute('CREATE TABLE phase7_flow.documents ('
                'id text PRIMARY KEY, title text NOT NULL, version integer NOT NULL, '
                'deleted boolean NOT NULL DEFAULT false, artifact jsonb NOT NULL)')
            conn.execute('CREATE TABLE phase7_flow.outbox ('
                'event_id bigserial PRIMARY KEY, doc_id text NOT NULL, version integer NOT NULL, '
                'processed boolean NOT NULL DEFAULT false, UNIQUE(doc_id,version))')
        with conn.transaction():
            conn.execute('INSERT INTO phase7_flow.documents VALUES (%s,%s,1,false,%s)',
                (doc_id, 'initial dataset', Jsonb({'key': manifest_key, 'version': manifest_version})))
            conn.execute('INSERT INTO phase7_flow.outbox(doc_id,version) VALUES (%s,1)', (doc_id,))
        assert source() == ('initial dataset', 1, False)
        assert conn.execute('SELECT count(*) FROM phase7_flow.outbox').fetchone()[0] == 1
        project()
        assert search.get('/' + index + '/_doc/' + doc_id).json()['_source']['title'] == 'initial dataset'

        # A metadata transaction either commits the new source and event together
        # or leaves both unchanged; the S3 object alone never publishes a dataset.
        try:
            with conn.transaction():
                conn.execute('UPDATE phase7_flow.documents SET title=%s,version=2 WHERE id=%s',
                    ('rolled back', doc_id))
                conn.execute('INSERT INTO phase7_flow.outbox(doc_id,version) VALUES (%s,2)', (doc_id,))
                raise RuntimeError('synthetic transaction failure')
        except RuntimeError:
            pass
        assert source() == ('initial dataset', 1, False)
        assert conn.execute('SELECT count(*) FROM phase7_flow.outbox').fetchone()[0] == 1

        with conn.transaction():
            conn.execute('UPDATE phase7_flow.documents SET title=%s,version=2 WHERE id=%s',
                ('updated dataset', doc_id))
            conn.execute('INSERT INTO phase7_flow.outbox(doc_id,version) VALUES (%s,2)', (doc_id,))
        assert source() == ('updated dataset', 2, False)
        assert search.get('/' + index + '/_doc/' + doc_id).json()['_source']['title'] == 'initial dataset'
        project()
        assert search.get('/' + index + '/_doc/' + doc_id).json()['_source']['title'] == 'updated dataset'
        with conn.transaction():
            conn.execute('UPDATE phase7_flow.documents SET deleted=true,version=3 WHERE id=%s', (doc_id,))
            conn.execute('INSERT INTO phase7_flow.outbox(doc_id,version) VALUES (%s,3)', (doc_id,))
        assert source() == ('updated dataset', 3, True)
        project()
        assert search.get('/' + index + '/_doc/' + doc_id).status_code == 404
        assert conn.execute('SELECT count(*) FROM phase7_flow.outbox WHERE processed').fetchone()[0] == 3
        print('PASS deployed bound artifact reference, atomic metadata/outbox, PostgreSQL-authoritative search create/update/delete')
    finally:
        search.close()
        conn.close()


if __name__ == '__main__':
    main()
