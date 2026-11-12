"""Regression checks for production Compose paths and partial fixture cleanup."""

import contextlib
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptFixtureTests(unittest.TestCase):
    def test_partial_artifact_setup_deletes_only_versions_already_created(self):
        module = load(
            "application_data_fixture",
            "scripts/tests/platform/verify-application-data-flow.py",
        )
        store = Mock()
        store.put_object.side_effect = [
            {"VersionId": "data-version"},
            {"VersionId": "manifest-version"},
            OSError("interrupted upload"),
        ]
        environment = {
            "FIXTURE_PARQUET_B64": "UEFSMVBBUjE=",
            "ARTIFACT_AWS_ENDPOINT_URL_S3": "http://fixture.invalid",
            "ARTIFACT_AWS_ACCESS_KEY_ID": "synthetic",
            "ARTIFACT_AWS_SECRET_ACCESS_KEY": "synthetic",
            "ARTIFACT_AWS_DEFAULT_REGION": "us-east-1",
            "ARTIFACT_S3_BUCKET": "fixture-bucket",
        }
        with (
            patch.dict(os.environ, environment),
            patch.object(module.boto3, "client", return_value=store),
            self.assertRaisesRegex(OSError, "interrupted upload"),
            contextlib.ExitStack() as cleanup,
        ):
            module.verify(cleanup)
        self.assertEqual(store.delete_object.call_count, 2)
        deleted = [call.kwargs for call in store.delete_object.call_args_list]
        self.assertEqual(
            {item["VersionId"] for item in deleted},
            {"data-version", "manifest-version"},
        )
        self.assertTrue(all(item["Bucket"] == "fixture-bucket" for item in deleted))
        prefix = deleted[0]["Key"].rsplit("/", 1)[0]
        self.assertTrue(all(item["Key"].startswith(prefix + "/") for item in deleted))
        store.delete_bucket.assert_not_called()


if __name__ == "__main__":
    unittest.main()
