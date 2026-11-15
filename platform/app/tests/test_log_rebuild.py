"""Retained logs must survive a complete rewrite of shared Loki storage."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from app.lifecycle import log_rebuild


class Loki:
    def __init__(self, tenant):
        self.tenant = tenant
        self.labels = {"job": "kubernetes-workloads", "component": "web"}
        self.entries = [[str(time.time_ns()), "retained log"]]
        self.truncate = False
        self.drop_writes = False

    def get(self, path, *, params=None, headers=None):
        if path == "/ready":
            return Mock(status_code=200)
        own = headers["X-Scope-OrgID"] == self.tenant
        if path.endswith("/series"):
            data = [self.labels] if own and self.entries else []
        elif path.endswith("/query_range"):
            values = (
                [
                    entry
                    for entry in self.entries
                    if int(entry[0]) >= int(params["start"])
                ]
                if own
                else []
            )
            if self.truncate:
                values = []
            data = {"result": [{"values": values[: params["limit"]]}] if values else []}
        else:
            data = {"result": [{"value": [0, str(len(self.entries))]}] if own else []}
        return Mock(json=lambda: {"data": data})

    def post(self, path, *, json, headers):
        if not self.drop_writes:
            self.entries.extend(json["streams"][0]["values"])
        return Mock(status_code=204)


class LogRebuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        environment = patch.dict(
            os.environ, {"PLATFORM_MAINTENANCE_DIR": self.temporary.name}
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.removed, self.retained = str(uuid4()), str(uuid4())
        self.operation = {"operation_id": str(uuid4()), "project_id": self.removed}
        self.conn = Mock()
        self.conn.execute.return_value.fetchall.return_value = [(self.retained,)]
        self.loki = Loki(self.retained)
        self.path = Path(self.temporary.name) / (
            self.operation["operation_id"] + ".loki-clean.jsonl"
        )

    def test_complete_export_excludes_deleted_tenant_and_replay_checks_retained_data(
        self,
    ):
        expected = list(self.loki.entries)
        log_rebuild.export(self.conn, self.operation, self.loki)
        self.assertNotIn(self.removed, self.path.read_text())
        self.assertIn(self.retained, self.path.read_text())
        self.loki.entries = []
        log_rebuild.restore(self.operation, self.loki)
        self.assertEqual(self.loki.entries, expected)

    def test_truncated_export_does_not_publish_a_safe_to_erase_file(self):
        self.loki.truncate = True
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            log_rebuild.export(self.conn, self.operation, self.loki)
        self.assertFalse(self.path.exists())

    def test_missing_replayed_data_cannot_pass_verification(self):
        log_rebuild.export(self.conn, self.operation, self.loki)
        self.loki.entries = []
        self.loki.drop_writes = True
        with self.assertRaisesRegex(ValueError, "verification failed"):
            log_rebuild.restore(self.operation, self.loki)

    def test_oversized_timestamp_tie_blocks_before_erasure(self):
        self.loki.entries *= 3
        with (
            patch.object(log_rebuild, "PAGE_SIZE", 2),
            self.assertRaisesRegex(ValueError, "timestamp group"),
        ):
            log_rebuild.export(self.conn, self.operation, self.loki)
        self.assertFalse(self.path.exists())

    def test_completed_export_is_reused_after_restart(self):
        log_rebuild.export(self.conn, self.operation, self.loki)
        original = self.path.read_text()
        self.loki.entries = []
        log_rebuild.export(self.conn, self.operation, self.loki)
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(
            json.loads(original.splitlines()[0])["tenants"], ["platform", self.retained]
        )
