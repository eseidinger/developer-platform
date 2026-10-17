"""Application-owned, checksum-verified Parquet snapshots in a named S3 bucket.

References identify exact S3 object versions, never a mutable "latest" key.
This is logical immutability, not WORM: authorized writers can delete versions.
"""
from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

MAX_PARQUET = 512 * 1024 * 1024
MAX_MANIFEST = 64 * 1024


@dataclass(frozen=True)
class ObjectVersion:
    key: str
    version_id: str
    sha256: str
    bytes: int

    def validate(self, limit):
        if (not re.fullmatch(r'datasets/[a-f0-9]{32}/(?:data\.parquet|manifest\.json)', self.key)
                or not isinstance(self.version_id, str) or not 1 <= len(self.version_id) <= 1024
                or self.version_id == 'null' or not re.fullmatch('[a-f0-9]{64}', self.sha256)
                or type(self.bytes) is not int or not 0 < self.bytes <= limit):
            raise ValueError('Invalid versioned artifact reference')


class Artifacts:
    def __init__(self, client, bucket):
        # The bucket comes from the explicit component binding, never a manifest.
        self.client, self.bucket = client, bucket

    def _put(self, key, body, digest, size, content_type):
        result = self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
            ContentLength=size, ContentType=content_type, Metadata={'sha256': digest})
        reference = ObjectVersion(key, result.get('VersionId'), digest, size)
        reference.validate(MAX_PARQUET)
        return reference

    def publish(self, parquet):
        parquet = Path(parquet)
        size = parquet.stat().st_size
        if not 0 < size <= MAX_PARQUET:
            raise ValueError('Parquet snapshot exceeds its publication budget')
        prefix = 'datasets/' + uuid4().hex + '/'
        # Keep the same file descriptor for checksum and upload. Callers must not
        # mutate a snapshot during publication; readers verify its exact bytes.
        with parquet.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
            source.seek(0)
            data = self._put(prefix + 'data.parquet', source, digest, size, 'application/vnd.apache.parquet')
        manifest = json.dumps({'schema_version': 1, 'format': 'parquet', 'object': asdict(data)},
            sort_keys=True, separators=(',', ':')).encode()
        return self._put(prefix + 'manifest.json', manifest, hashlib.sha256(manifest).hexdigest(),
            len(manifest), 'application/json')

    def _read(self, reference, output, limit):
        reference.validate(limit)
        result = self.client.get_object(Bucket=self.bucket, Key=reference.key, VersionId=reference.version_id)
        with closing(result['Body']) as stream:
            if result['ContentLength'] != reference.bytes or result.get('VersionId') != reference.version_id:
                raise ValueError('Artifact length/version mismatch')
            digest, total = hashlib.sha256(), 0
            while part := stream.read(65536):
                total += len(part)
                if total > reference.bytes:
                    raise ValueError('Artifact exceeded its declared size')
                digest.update(part)
                output.write(part)
            if total != reference.bytes or digest.hexdigest() != reference.sha256:
                raise ValueError('Artifact checksum mismatch')

    def materialize(self, reference, destination):
        """Verify a manifest and its exact Parquet version before publishing locally."""
        import io
        import tempfile
        manifest = io.BytesIO()
        self._read(reference, manifest, MAX_MANIFEST)
        value = json.loads(manifest.getvalue())
        if value.get('schema_version') != 1 or value.get('format') != 'parquet':
            raise ValueError('Unsupported artifact manifest')
        data = ObjectVersion(**value['object'])
        if data.key != reference.key.removesuffix('manifest.json') + 'data.parquet':
            raise ValueError('Manifest object belongs to another snapshot')
        destination = Path(destination)
        # TemporaryDirectory ensures a failed verification leaves no partial file.
        with tempfile.TemporaryDirectory(prefix='verified-artifact-', dir=destination.parent) as directory:
            staged = Path(directory) / 'data.parquet'
            with staged.open('wb') as output:
                self._read(data, output, MAX_PARQUET)
            staged.chmod(0o600)
            # Same-directory hard-link publication is atomic and refuses an
            # existing destination, including a concurrent writer's new file.
            destination.hardlink_to(staged)
        return destination


if __name__ == '__main__':
    import argparse
    import os
    import boto3
    from botocore.config import Config
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    publish = commands.add_parser('publish')
    publish.add_argument('parquet', type=Path)
    read = commands.add_parser('read')
    read.add_argument('reference', type=Path)
    read.add_argument('destination', type=Path)
    arguments = parser.parse_args()
    client = boto3.client('s3', config=Config(s3={'addressing_style': 'path'},
        connect_timeout=5, read_timeout=30, retries={'max_attempts': 2},
        request_checksum_calculation='when_required', response_checksum_validation='when_required'))
    artifacts = Artifacts(client, os.environ['S3_BUCKET'])
    if arguments.command == 'publish':
        print(json.dumps(asdict(artifacts.publish(arguments.parquet)), sort_keys=True))
    else:
        artifacts.materialize(ObjectVersion(**json.loads(arguments.reference.read_text())), arguments.destination)
