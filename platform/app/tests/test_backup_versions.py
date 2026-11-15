"""S3 versioning must not preserve erased restic packs or snapshot metadata."""

import unittest
from unittest.mock import Mock

from app.lifecycle.backup_versions import erase


class BackupVersionTests(unittest.TestCase):
    def client(self, page, verified=None):
        client = Mock()
        client.get_paginator.return_value.paginate.side_effect = [
            [page],
            [verified or {}],
        ]
        client.delete_objects.return_value = {}
        return client

    def test_removes_noncurrent_versions_and_markers_preserving_current_clean_objects(
        self,
    ):
        page = {
            "Versions": [
                {"Key": "repo/data/pack", "VersionId": "old", "IsLatest": False},
                {"Key": "repo/data/pack", "VersionId": "clean", "IsLatest": True},
            ],
            "DeleteMarkers": [
                {"Key": "repo/snapshots/dirty", "VersionId": "marker", "IsLatest": True}
            ],
        }
        client = self.client(page)
        erase(client, "bucket", "repo/")
        self.assertEqual(
            client.delete_objects.call_args.kwargs["Delete"]["Objects"],
            [
                {"Key": "repo/data/pack", "VersionId": "old"},
                {"Key": "repo/snapshots/dirty", "VersionId": "marker"},
            ],
        )
        self.assertEqual(client.get_paginator.return_value.paginate.call_count, 2)

    def test_object_lock_errors_block_completion(self):
        client = self.client(
            {"Versions": [{"Key": "repo/pack", "VersionId": "old", "IsLatest": False}]}
        )
        client.delete_objects.return_value = {"Errors": [{"Code": "AccessDenied"}]}
        with self.assertRaisesRegex(ValueError, "could not be erased"):
            erase(client, "bucket", "repo/")

    def test_relisting_detects_historical_versions_left_after_pagination(self):
        page = {
            "Versions": [{"Key": "repo/pack", "VersionId": "old", "IsLatest": False}]
        }
        with self.assertRaisesRegex(ValueError, "versions remain"):
            erase(self.client(page, page), "bucket", "repo/")

    def test_unversioned_current_objects_need_no_deletion(self):
        client = self.client(
            {"Versions": [{"Key": "repo/pack", "VersionId": "null", "IsLatest": True}]}
        )
        erase(client, "bucket", "repo/")
        client.delete_objects.assert_not_called()
