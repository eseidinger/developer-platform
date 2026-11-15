"""Host erasure never follows arbitrary paths or deletes another tenant."""

import importlib.util
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
            with patch.object(maintenance, "command") as command:
                maintenance.remove_tenant(root, identity, storage)
            self.assertFalse(own.exists())
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
