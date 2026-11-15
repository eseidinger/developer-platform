"""Host erasure never follows arbitrary paths or deletes another tenant."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "project_erasure", ROOT / "operations/maintenance/scripts/purge-project.py"
)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


class TenantErasureTests(unittest.TestCase):
    def test_workload_logs_are_removed_only_from_kubernetes_nodes(self):
        def execute(arguments, root):
            if arguments[:2] == ["docker", "ps"]:
                return (
                    b"k3d-workloads-serverlb\n"
                    b"k3d-workloads-server-0\n"
                    b"k3d-workloads-agent-0\n"
                )
            if arguments[2] == "k3d-workloads-serverlb":
                raise maintenance.MaintenanceError("Load balancer has no pod logs")
            return b""

        with patch.object(maintenance, "command", side_effect=execute) as command:
            maintenance.remove_workload_logs(Path("/unused"), "demo")
        nodes = {
            call.args[0][2]
            for call in command.call_args_list
            if call.args[0][:2] == ["docker", "exec"]
        }
        self.assertEqual(nodes, {"k3d-workloads-server-0", "k3d-workloads-agent-0"})

    def test_erases_the_exact_uuid_and_restarts_storage(self):
        identity = str(uuid4())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "tempo"
            own = storage / "blocks" / identity
            other = storage / "blocks" / str(uuid4())
            own.mkdir(parents=True)
            other.mkdir()
            (own / "block").write_text("erase")
            (other / "block").write_text("retain")
            (storage / "shard_001.json").write_text(
                json.dumps(
                    {
                        "jobs": {
                            "own": {"tenant": identity},
                            "other": {"tenant": other.name},
                        }
                    }
                )
            )
            with patch.object(maintenance, "command") as command:
                maintenance.remove_tenant(root, identity, storage)
            self.assertFalse(own.exists())
            self.assertEqual(
                json.loads((storage / "shard_001.json").read_text())["jobs"],
                {"other": {"tenant": other.name}},
            )
            self.assertEqual((other / "block").read_text(), "retain")
            self.assertEqual(
                command.call_args_list[0].args[0],
                ["docker", "compose", "stop", "tempo"],
            )
            self.assertEqual(
                command.call_args_list[-1].args[0],
                ["docker", "compose", "start", "tempo"],
            )

    def test_rejects_a_storage_symlink_before_stopping_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "actual"
            target.mkdir()
            link = root / "tempo"
            link.symlink_to(target, target_is_directory=True)
            with (
                patch.object(maintenance, "command") as command,
                self.assertRaises(maintenance.MaintenanceError),
            ):
                maintenance.remove_tenant(root, str(uuid4()), link)
            command.assert_not_called()

    def test_metric_rebuild_resumes_from_durable_clean_copy_without_a_live_server(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = str(uuid4())
            staging = root / ".runtime/maintenance" / (identity + ".metrics-clean")
            staging.mkdir(parents=True)
            (staging / "clean-block").mkdir()
            (staging / "clean-block/index").write_text("retained metrics")
            storage = root / "prometheus"
            storage.mkdir()
            (storage / "old-wal").write_text("erased metrics")
            with (
                patch.object(maintenance, "command"),
                patch.object(maintenance, "api") as api,
                patch.object(maintenance, "volume_root", return_value=storage),
            ):
                maintenance.compact_metrics(root, {"operation_id": identity})
            api.assert_not_called()
            self.assertFalse((storage / "old-wal").exists())
            self.assertEqual(
                (storage / "clean-block/index").read_text(), "retained metrics"
            )
            self.assertFalse(staging.exists())

    def test_report_erasure_preserves_unrelated_run_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / ".runtime/hosted-access"
            for name, project in (("own", "demo"), ("other", "another")):
                run = reports / name
                run.mkdir(parents=True)
                (run / "report.json").write_text(
                    json.dumps({"projects": {"provider": project}})
                )
            maintenance.remove_reports(
                root, {"project": "demo", "project_id": str(uuid4())}
            )
            self.assertFalse((reports / "own").exists())
            self.assertTrue((reports / "other/report.json").exists())

    def test_failed_clean_backup_cannot_reuse_a_preceding_verified_snapshot(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = root / "backup.json"
            configuration.write_text("{}")
            job = Mock(state=root)
            job.read.return_value = {
                "run_id": "old",
                "result": "success",
                "last_verified_snapshot": "old",
                "last_verified_capture": 1,
                "started": 1,
            }
            module = SimpleNamespace(Job=lambda _: job)
            with (
                patch.object(
                    maintenance.importlib.util,
                    "spec_from_file_location",
                    return_value=Mock(),
                ),
                patch.object(
                    maintenance.importlib.util, "module_from_spec", return_value=module
                ),
                self.assertRaisesRegex(
                    maintenance.MaintenanceError, "No verified clean backup"
                ),
            ):
                maintenance.clean_backups(
                    root, str(uuid4()), configuration, str(uuid4())
                )
            job.command.assert_not_called()
