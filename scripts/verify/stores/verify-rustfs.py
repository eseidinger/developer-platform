#!/usr/bin/env python3
"""Disposable pinned RustFS acceptance. No live resources, credentials or notifications."""

import sys
from pathlib import Path

# Support direct invocation as well as imports from repository tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
import secrets
import subprocess
import time
from uuid import uuid4

from botocore.exceptions import ClientError
from app.stores import catalog
from app.stores.http_relay import access_key
from app.stores.relay import Relay
from app.stores.s3 import S3, bucket, client, StoreError, parent
from scripts.fixtures.store_volume_fixture import restored

IMAGE = 'rustfs/rustfs:1.0.2@sha256:7e948dad4748bda48f8985fda7195f8cf2e4259427011f6120acc2c9acf51587'


def command(*arguments, env=None):
    result = subprocess.run(arguments, env=env, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Disposable RustFS fixture command failed')
    return result.stdout.decode().strip()


def denied(operation, invalid_key=False):
    try:
        operation()
    except ClientError as error:
        status = error.response['ResponseMetadata']['HTTPStatusCode']
        assert status in {401, 403} or (invalid_key and status == 400
            and error.response['Error']['Code'] in {'InvalidRequest', 'InvalidAccessKeyId', 'ExpiredToken'}), 'Expected authorization denial'
    else:
        raise AssertionError('Scoped RustFS credential exceeded permissions')


def main():
    name = 'named-rustfs-' + uuid4().hex[:12]
    volume = name + '-data'
    key, secret = secrets.token_hex(10), secrets.token_hex(32)
    os.environ['DATABASE_KEY'] = secrets.token_hex(32)
    env = {**os.environ, 'RUSTFS_ACCESS_KEY': key, 'RUSTFS_SECRET_KEY': secret}
    try:
        command('docker', 'run', '-d', '--name', name, '--memory', '768m', '--cpus', '1',
            '--mount', f'type=volume,src={volume},dst=/data', '--tmpfs', '/logs:rw,uid=10001,gid=10001,size=16m',
            '-e', 'RUSTFS_ACCESS_KEY', '-e', 'RUSTFS_SECRET_KEY', '-e', 'RUSTFS_VOLUMES=/data',
            '-e', 'RUSTFS_SCANNER_CYCLE=1',
            '-e', 'RUSTFS_OBS_LOG_DIRECTORY=/logs', '-p', '127.0.0.1::9000', IMAGE, env=env)
        port = int(command('docker', 'port', name, '9000/tcp').rsplit(':', 1)[1])
        endpoint = f'http://127.0.0.1:{port}'
        provider = S3(endpoint, key, secret)
        for _ in range(100):
            try:
                provider.root.list_buckets()
                break
            except Exception:
                time.sleep(.2)
        else:
            raise AssertionError('Disposable RustFS not ready')
        first, other = ({'resource_id': str(uuid4()), 'quota_bytes': 16 * 1024 * 1024} for _ in range(2))
        for resource in (first, other):
            for _ in range(100):
                try:
                    provider.provision(resource)
                    break
                except StoreError:
                    time.sleep(.25)
            else:
                raise AssertionError('RustFS quota admission never became ready')
            provider.provision(resource)
        credentials = []
        for mode in ('read-write', 'read-only'):
            cred = {'credential_id': str(uuid4()), 'mode': mode,
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            provider.issue(first, cred)
            provider.issue(first, cred)
            provider.probe(first, cred)
            credentials.append(cred)
        writer, reader = credentials

        def scoped(cred, url=None):
            return client(url or endpoint, access_key(cred['credential_id']), catalog.secret_for(cred['credential_id']))

        rw, ro = scoped(writer), scoped(reader)
        bucket_name = bucket(first)
        first_version = rw.put_object(Bucket=bucket_name, Key='source.parquet', Body=b'first-version')['VersionId']
        second_version = rw.put_object(Bucket=bucket_name, Key='source.parquet', Body=b'second-version')['VersionId']
        assert first_version != second_version
        assert ro.get_object(Bucket=bucket_name, Key='source.parquet', VersionId=first_version)['Body'].read() == b'first-version'
        assert ro.get_object(Bucket=bucket_name, Key='source.parquet')['Body'].read() == b'second-version'
        denied(lambda: ro.put_object(Bucket=bucket_name, Key='forbidden', Body=b'forbidden'))
        denied(lambda: ro.delete_object(Bucket=bucket_name, Key='source.parquet'))
        denied(lambda: rw.get_object(Bucket=bucket(other), Key='foreign'))
        denied(lambda: rw.list_objects_v2(Bucket=bucket(other)))
        denied(lambda: rw.delete_bucket(Bucket=bucket_name))
        denied(lambda: rw.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={'Status': 'Suspended'}))
        denied(lambda: rw.put_bucket_policy(Bucket=bucket_name, Policy='{"Version":"2012-10-17","Statement":[]}'))
        # No derived identity may mint, update or enumerate broader credentials.
        attacker = S3(endpoint, access_key(writer['credential_id']), catalog.secret_for(writer['credential_id']))
        for method, path, body, query in (
            ('GET', 'list-users', None, {}),
            ('PUT', 'add-service-account', {'targetUser': key, 'accessKey': secrets.token_hex(10), 'secretKey': secrets.token_hex(32)}, {}),
            ('PUT', 'add-service-account', {'targetUser': parent(writer), 'accessKey': secrets.token_hex(10), 'secretKey': secrets.token_hex(32)}, {}),
            ('POST', 'update-service-account', {'expiration': '2099-01-01T00:00:00Z'}, {'accessKey': access_key(writer['credential_id'])})):
            try:
                attacker.admin(method, path, body, **query)
            except StoreError:
                pass
            else:
                raise AssertionError('Scoped S3 identity could administer credentials')

        async def relay_roundtrip():
            lease = {**reader, 'provider': 's3', 'resource_id': first['resource_id'],
                'expires_at': datetime.now(timezone.utc) + timedelta(seconds=2)}
            relay = Relay(backend=lambda lease: ('127.0.0.1', port))
            relay.leases = {20000: lease}
            relay.last_success = time.monotonic()
            server = await asyncio.start_server(lambda r, w: relay.handle(20000, r, w), '127.0.0.1', 0)
            local = f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}'
            try:
                result = await asyncio.to_thread(lambda: scoped(reader, local).get_object(Bucket=bucket_name, Key='source.parquet')['Body'].read())
                assert result == b'second-version'
                # Streaming upload through the strict HTTP parser preserves SigV4.
                relay.leases[20000] = {**lease, **writer, 'expires_at': datetime.now(timezone.utc) + timedelta(seconds=2)}
                payload = b'versioned-binary-source\0' * 300000
                await asyncio.to_thread(lambda: scoped(writer, local).put_object(Bucket=bucket_name, Key='streamed.bin', Body=io.BytesIO(payload)))
                assert hashlib.sha256(ro.get_object(Bucket=bucket_name, Key='streamed.bin')['Body'].read()).digest() == hashlib.sha256(payload).digest()
                relay.leases.clear()
                native = scoped(writer, local)
                try:
                    await asyncio.to_thread(lambda: native.list_objects_v2(Bucket=bucket_name))
                except Exception:
                    pass
                else:
                    raise AssertionError('Revoked relay lease remained usable')
            finally:
                relay.leases.clear()
                server.close()
                await server.wait_closed()
        asyncio.run(relay_roundtrip())
        try:
            rw.put_object(Bucket=bucket_name, Key='over-quota.bin', Body=b'q' * (17 * 1024 * 1024))
        except ClientError as error:
            assert error.response['Error']['Code'] == 'InvalidRequest' and error.response['Error']['Message'].startswith('Bucket quota exceeded.'), 'Expected native quota denial'
        else:
            raise AssertionError('RustFS accepted growth past its hard quota')
        assert ro.get_object(Bucket=bucket_name, Key='source.parquet')['Body'].read() == b'second-version'
        rw.delete_object(Bucket=bucket_name, Key='streamed.bin')
        provider.root.put_object(Bucket=bucket(other), Key='unaffected', Body=b'other-resource')
        first['quota_bytes'] = 32 * 1024 * 1024
        provider.provision(first)
        rw.put_object(Bucket=bucket_name, Key='after-approved-increase.bin', Body=b'q' * (17 * 1024 * 1024))
        assert provider.usage(first) > 0
        provider.validate_recovery(first)
        analytics_reference = None
        if os.environ.get('STORE_ANALYTICS_FIXTURE') == '1':
            from scripts.fixtures.store_analytics_fixture import publish
            analytics_reference = publish(rw, ro, bucket_name)
        with restored(name, volume, '/data', IMAGE, ['--memory', '768m', '--cpus', '1',
                '--tmpfs', '/logs:rw,uid=10001,gid=10001,size=16m', '-e', 'RUSTFS_ACCESS_KEY', '-e', 'RUSTFS_SECRET_KEY',
                '-e', 'RUSTFS_VOLUMES=/data', '-e', 'RUSTFS_OBS_LOG_DIRECTORY=/logs',
                '-p', '127.0.0.1::9000'], env) as recovered_name:
            recovered_port = int(command('docker', 'port', recovered_name, '9000/tcp').rsplit(':', 1)[1])
            recovered = S3(f'http://127.0.0.1:{recovered_port}', key, secret)
            for _ in range(100):
                try:
                    recovered.validate_recovery(first)
                    break
                except Exception:
                    time.sleep(.2)
            else:
                raise AssertionError('Restored RustFS bucket did not become ready')
            for old in credentials:
                recovered.revoke(first, old)
            old_reader = client(recovered.endpoint, access_key(reader['credential_id']), catalog.secret_for(reader['credential_id']))
            denied(lambda: old_reader.list_objects_v2(Bucket=bucket_name), invalid_key=True)
            fresh = {'credential_id': str(uuid4()), 'mode': 'read-only',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
            recovered.issue(first, fresh)
            fresh_reader = client(recovered.endpoint, access_key(fresh['credential_id']), catalog.secret_for(fresh['credential_id']))
            assert fresh_reader.get_object(Bucket=bucket_name, Key='source.parquet', VersionId=first_version)['Body'].read() == b'first-version'
            assert fresh_reader.get_object(Bucket=bucket_name, Key='after-approved-increase.bin')['ContentLength'] == 17 * 1024 * 1024
            if analytics_reference:
                from scripts.fixtures.store_analytics_fixture import recovered as recovered_analytics
                recovered_analytics(fresh_reader, bucket_name, analytics_reference)
            denied(lambda: fresh_reader.list_objects_v2(Bucket=bucket(other)))
            recovered.validate_recovery(other)
        print('PASS RustFS stopped-volume capture and empty-volume restore: versions/data/IAM retained; recovered keys revoked; fresh scoped approval reads retained data')
        port = int(command('docker', 'port', name, '9000/tcp').rsplit(':', 1)[1])
        endpoint = f'http://127.0.0.1:{port}'
        provider = S3(endpoint, key, secret)
        rw, ro = scoped(writer), scoped(reader)
        for _ in range(100):
            try:
                provider.validate_recovery(first)
                break
            except Exception:
                time.sleep(.2)
        else:
            raise AssertionError('Original RustFS did not recover after capture')
        expiring = {'credential_id': str(uuid4()), 'mode': 'read-only',
            'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()}
        provider.issue(first, expiring)
        time.sleep(2.2)
        denied(lambda: scoped(expiring).list_objects_v2(Bucket=bucket_name), invalid_key=True)
        for credential in [*credentials, expiring]:
            provider.revoke(first, credential)
            provider.revoke(first, credential)
        denied(lambda: ro.list_objects_v2(Bucket=bucket_name), invalid_key=True)
        for _ in range(10):
            try:
                provider.purge(first)
                break
            except StoreError:
                pass
        else:
            raise AssertionError('Versioned purge did not complete')
        provider.validate_recovery(other)
        print('PASS pinned RustFS: isolated versioned buckets, RO/RW, native expiry/revocation, denied credential administration, idempotent lifecycle, signed streaming relay, hard quota/retained reads/cleanup/approved increase, measured usage and isolated version purge')
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
