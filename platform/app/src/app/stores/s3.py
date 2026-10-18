"""RustFS-backed named, versioned buckets and expiring derived credentials."""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener
from uuid import UUID

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.exceptions import ClientError

from . import catalog
from .http_relay import access_key, console_user


class StoreError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def bucket(resource):
    return 'resource-' + UUID(str(resource['resource_id'])).hex


def parent(credential):
    return 'parent-' + UUID(str(credential['credential_id'])).hex


def console_secret(credential):
    return hmac.new(os.environ['DATABASE_KEY'].encode(),
        ('native-s3-console-v1:' + str(UUID(str(credential['credential_id'])))).encode(), hashlib.sha256).hexdigest()


def client(endpoint, key, secret):
    return boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=key,
        aws_secret_access_key=secret, region_name='us-east-1', config=Config(
            connect_timeout=2, read_timeout=5, retries={'max_attempts': 1},
            s3={'addressing_style': 'path'}, request_checksum_calculation='when_required',
            response_checksum_validation='when_required'))


def policy(resource, mode):
    name = bucket(resource)
    objects = ['s3:GetObject', 's3:GetObjectVersion']
    listing = ['s3:GetBucketLocation', 's3:ListBucket', 's3:ListBucketVersions']
    if mode == 'read-write':
        objects += ['s3:PutObject', 's3:DeleteObject', 's3:DeleteObjectVersion',
                    's3:AbortMultipartUpload', 's3:ListMultipartUploadParts']
        listing += ['s3:ListBucketMultipartUploads']
    return {'Version': '2012-10-17', 'Statement': [
        *[{'Effect': 'Deny', 'Action': [family + ':*'], 'Resource': ['arn:aws:s3:::*']}
          for family in ('admin', 'sts', 'kms')],
        {'Effect': 'Allow', 'Action': listing, 'Resource': ['arn:aws:s3:::' + name]},
        {'Effect': 'Allow', 'Action': objects, 'Resource': ['arn:aws:s3:::' + name + '/*']}]}


def console_policy(resource, mode):
    value = policy(resource, mode)
    value['Statement'] = [item for item in value['Statement'] if item['Action'] != ['sts:*']]
    value['Statement'].append({'Effect': 'Allow', 'Action': ['sts:AssumeRole'], 'Resource': ['arn:aws:s3:::*']})
    return value


class S3:
    def __init__(self, endpoint=None, key=None, secret=None):
        self.endpoint = endpoint or 'http://' + os.environ['RUSTFS_IP'] + ':9000'
        self.key = key or os.environ['RUSTFS_ACCESS_KEY']
        self.secret = secret or os.environ['RUSTFS_SECRET_KEY']
        self.root = client(self.endpoint, self.key, self.secret)

    def admin(self, method, path, body=None, missing=False, **query):
        url = self.endpoint + '/rustfs/admin/v3/' + path
        if query:
            url += '?' + urlencode(query)
        data = json.dumps(body, separators=(',', ':')).encode() if body is not None else b''
        request = AWSRequest(method=method, url=url, data=data, headers={'Content-Type': 'application/json',
            'X-Amz-Content-SHA256': hashlib.sha256(data).hexdigest()})
        from botocore.credentials import Credentials
        SigV4Auth(Credentials(self.key, self.secret), 's3', 'us-east-1').add_auth(request)
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(Request(url, data=data if method in {'PUT', 'POST'} else None,
                    method=method, headers=dict(request.headers)), timeout=5) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise StoreError('Store administration response exceeded its limit')
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            if missing and error.code == 404:
                return None
            raise StoreError('Store administration failed') from None

    def provision(self, resource):
        name = bucket(resource)
        try:
            self.root.head_bucket(Bucket=name)
        except ClientError as error:
            if error.response['ResponseMetadata']['HTTPStatusCode'] != 404:
                raise StoreError('Bucket availability check failed') from None
            self.root.create_bucket(Bucket=name)
        self.root.put_bucket_versioning(Bucket=name, VersioningConfiguration={'Status': 'Enabled'})
        self.admin('PUT', 'set-bucket-quota', {'quota': resource['quota_bytes'], 'quota_type': 'HARD'}, bucket=name)
        checked = self.admin('POST', 'quota-check/' + name, {'operation_type': 'PUT', 'operation_size': 0})
        if checked.get('quota_limit') != resource['quota_bytes']:
            raise StoreError('Bucket quota readiness or configuration mismatch')
        for mode in ('read-only', 'read-write'):
            self.admin('PUT', 'add-canned-policy', policy(resource, mode), name=name + '-' + mode)
            self.admin('PUT', 'add-canned-policy', console_policy(resource, mode), name=name + '-' + mode + '-console')

    def issue(self, resource, credential):
        if credential.get('kind') == 'human':
            user = console_user(credential['credential_id'])
            self.admin('PUT', 'add-user', {'secretKey': console_secret(credential), 'status': 'enabled'}, accessKey=user)
            self.admin('PUT', 'set-user-or-group-policy', policyName=bucket(resource) + '-' + credential['mode'] + '-console',
                userOrGroup=user, isGroup='false')
        user, key = parent(credential), access_key(credential['credential_id'])
        secret = catalog.secret_for(credential['credential_id'])
        parent_secret = hmac.new(secret.encode(), b'non-disclosed-parent-v1', hashlib.sha256).hexdigest()
        self.admin('PUT', 'add-user', {'secretKey': parent_secret, 'status': 'enabled'}, accessKey=user)
        self.admin('PUT', 'set-user-or-group-policy', policyName=bucket(resource) + '-' + credential['mode'],
            userOrGroup=user, isGroup='false')
        expiration = credential['expires_at']
        if isinstance(expiration, datetime):
            expiration = expiration.isoformat()
        body = {'accessKey': key, 'secretKey': secret, 'targetUser': user,
                'expiration': expiration, 'policy': policy(resource, credential['mode'])}
        existing = self.admin('GET', 'info-service-account', missing=True, accessKey=key)
        if existing is None:
            self.admin('PUT', 'add-service-account', body)
        else:
            if existing.get('parentUser') != user:
                raise StoreError('Derived credential ownership mismatch')
            self.admin('POST', 'update-service-account', {k: v for k, v in body.items()
                if k not in {'targetUser', 'accessKey'}}, accessKey=key)

    def revoke(self, resource, credential):
        key, user = access_key(credential['credential_id']), parent(credential)
        # RustFS 1.0.2 returns 400 for an already absent service-account DELETE;
        # its info endpoint provides an unambiguous 404 for idempotent cleanup.
        existing = self.admin('GET', 'info-service-account', missing=True, accessKey=key)
        if existing is not None:
            if existing.get('parentUser') != user:
                raise StoreError('Derived credential ownership mismatch')
            self.admin('DELETE', 'delete-service-account', accessKey=key)
        if self.admin('GET', 'user-info', missing=True, accessKey=user) is not None:
            self.admin('DELETE', 'remove-user', accessKey=user)
        console = console_user(credential['credential_id'])
        if self.admin('GET', 'user-info', missing=True, accessKey=console) is not None:
            self.admin('DELETE', 'remove-user', accessKey=console)
        # Admin deletion can precede the restored server's IAM cache refresh.
        # Recovery must not release quarantine while the old native key works.
        try:
            self.root.head_bucket(Bucket=bucket(resource))
        except ClientError as error:
            if error.response['ResponseMetadata']['HTTPStatusCode'] == 404:
                return  # Already purged; there is no retained resource to read.
            raise StoreError('Revoked credential could not be verified') from None
        scoped = client(self.endpoint, key, catalog.secret_for(credential['credential_id']))
        for attempt in range(20):
            try:
                scoped.list_objects_v2(Bucket=bucket(resource), MaxKeys=1)
            except ClientError as error:
                status = error.response['ResponseMetadata']['HTTPStatusCode']
                code = error.response['Error']['Code']
                if status in {401, 403} or (status == 400 and code in
                        {'InvalidRequest', 'InvalidAccessKeyId', 'ExpiredToken'}):
                    return
                raise StoreError('Revoked credential could not be verified') from None
            if attempt < 19:
                time.sleep(.25)
        raise StoreError('Revoked credential remains active')

    def credentials(self, resource, credential):
        return {'AWS_ACCESS_KEY_ID': access_key(credential['credential_id']),
            'AWS_SECRET_ACCESS_KEY': catalog.secret_for(credential['credential_id']),
            'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ENDPOINT_URL_S3': self.endpoint, 'S3_BUCKET': bucket(resource),
            **({'RUSTFS_CONSOLE_ACCESS_KEY': console_user(credential['credential_id']),
                'RUSTFS_CONSOLE_SECRET_KEY': console_secret(credential)} if credential.get('kind') == 'human' else {})}

    def probe(self, resource, credential):
        scoped = client(self.endpoint, access_key(credential['credential_id']), catalog.secret_for(credential['credential_id']))
        scoped.list_objects_v2(Bucket=bucket(resource), MaxKeys=1)

    def usage(self, resource):
        total, pages = 0, 0
        for page in self.root.get_paginator('list_object_versions').paginate(Bucket=bucket(resource)):
            total += sum(v['Size'] for v in page.get('Versions', []))
            pages += 1
            if pages >= 64 and page.get('IsTruncated'):
                raise StoreError('Usage scan needs operator review')
        return total

    def validate_recovery(self, resource):
        # Missing retained data must never be recreated during reconciliation.
        self.root.head_bucket(Bucket=bucket(resource))
        if self.root.get_bucket_versioning(Bucket=bucket(resource)).get('Status') != 'Enabled':
            raise StoreError('Retained bucket versioning is missing')

    def purge(self, resource):
        name = bucket(resource)
        try:
            page = self.root.list_object_versions(Bucket=name, MaxKeys=500)
        except ClientError as error:
            if error.response['ResponseMetadata']['HTTPStatusCode'] != 404:
                raise
            page = None
        if page is not None:
            keys = [{'Key': item['Key'], 'VersionId': item['VersionId']}
                    for item in page.get('Versions', []) + page.get('DeleteMarkers', [])]
            if keys:
                result = self.root.delete_objects(Bucket=name, Delete={'Objects': keys, 'Quiet': True})
                if result.get('Errors'):
                    raise StoreError('Version cleanup incomplete')
                raise StoreError('Version cleanup in progress')
            uploads = self.root.list_multipart_uploads(Bucket=name, MaxUploads=16).get('Uploads', [])
            for upload in uploads:
                self.root.abort_multipart_upload(Bucket=name, Key=upload['Key'], UploadId=upload['UploadId'])
            if uploads:
                raise StoreError('Upload cleanup in progress')
            self.root.delete_bucket(Bucket=name)
        # A previous pass may have deleted the bucket before policy cleanup failed.
        # Native policy DELETE reports missing entries as an internal error; its
        # read endpoint supplies an unambiguous 404 for idempotent recovery.
        for mode in ('read-only', 'read-write'):
            for suffix in ('', '-console'):
                identity = name + '-' + mode + suffix
                if self.admin('GET', 'info-canned-policy', missing=True, name=identity) is not None:
                    self.admin('DELETE', 'remove-canned-policy', name=identity)
