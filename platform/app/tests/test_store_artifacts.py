import hashlib
import io
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "examples/analytics-artifacts")
)
from artifacts import Artifacts


class VersionedS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        data = Body.read() if hasattr(Body, "read") else Body
        version = str(len(self.objects) + 1)
        self.objects[(Bucket, Key, version)] = data
        return {"VersionId": version}

    def get_object(self, *, Bucket, Key, VersionId):
        data = self.objects[(Bucket, Key, VersionId)]
        return {
            "VersionId": VersionId,
            "ContentLength": len(data),
            "Body": io.BytesIO(data),
        }


class ArtifactBoundaryTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.parquet"
        self.source.write_bytes(b"synthetic immutable bytes" * 10000)
        self.store = VersionedS3()
        self.artifacts = Artifacts(self.store, "bound-bucket")
        self.reference = self.artifacts.publish(self.source)
        self.destination = self.root / "read.parquet"

    def test_new_versions_do_not_change_reference_and_existing_local_file_is_preserved(
        self,
    ):
        self.store.put_object(
            Bucket="bound-bucket", Key=self.reference.key, Body=b"newest manifest"
        )
        self.artifacts.materialize(self.reference, self.destination)
        self.assertEqual(self.destination.read_bytes(), self.source.read_bytes())
        self.destination.write_bytes(b"other local result")
        with self.assertRaises(FileExistsError):
            self.artifacts.materialize(self.reference, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"other local result")

    def test_corrupt_manifest_and_declared_length_leave_no_partial_file(self):
        for reference in (
            replace(self.reference, sha256="0" * 64),
            replace(self.reference, bytes=self.reference.bytes + 1),
        ):
            with self.assertRaises(ValueError):
                self.artifacts.materialize(reference, self.destination)
            self.assertFalse(self.destination.exists())

    def test_parquet_checksum_is_verified_even_with_a_valid_manifest(self):
        key = ("bound-bucket", self.reference.key, self.reference.version_id)
        manifest = json.loads(self.store.objects[key])
        manifest["object"]["sha256"] = "0" * 64
        raw = json.dumps(manifest).encode()
        self.store.objects[key] = raw
        reference = replace(
            self.reference, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        )
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.artifacts.materialize(reference, self.destination)
        self.assertFalse(self.destination.exists())

    def test_unversioned_unsafe_and_oversized_references_are_rejected(self):
        for value in (
            replace(self.reference, version_id="null"),
            replace(self.reference, key="../../private"),
            replace(self.reference, key="https://unbound.invalid/data"),
            replace(self.reference, bytes=65537),
        ):
            with self.assertRaises(ValueError):
                self.artifacts.materialize(value, self.destination)
        self.assertFalse(self.destination.exists())

    def test_manifest_cannot_redirect_to_another_snapshot(self):
        key = ("bound-bucket", self.reference.key, self.reference.version_id)
        value = json.loads(self.store.objects[key])
        value["object"]["key"] = "datasets/" + "a" * 32 + "/data.parquet"
        raw = json.dumps(value).encode()
        self.store.objects[key] = raw
        reference = replace(
            self.reference, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        )
        with self.assertRaisesRegex(ValueError, "another snapshot"):
            self.artifacts.materialize(reference, self.destination)
        self.assertFalse(self.destination.exists())
