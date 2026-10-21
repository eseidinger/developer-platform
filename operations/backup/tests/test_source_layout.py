"""Backup and restore must support checkout layouts on both sides of the move."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load_script("layout_backup", "backup-platform.py")
restore = load_script("layout_restore", "restore-recovery.py")


class ConfigurationLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("compose.yaml", ".env"):
            (self.root / name).touch()
        for name in ("scripts", "platform", "infrastructure"):
            (self.root / name).mkdir()

    def test_current_layout_is_captured_once_through_infrastructure(self):
        for component in ("identity", "persistence"):
            (self.root / "infrastructure" / component).mkdir()
        self.assertEqual(
            backup.configuration_sources(self.root),
            ["compose.yaml", ".env", "scripts", "platform", "infrastructure"],
        )

    def test_older_checkout_still_captures_both_service_directories(self):
        for component in ("identity", "persistence"):
            (self.root / component).mkdir()
        self.assertEqual(
            backup.configuration_sources(self.root)[-2:],
            ["identity", "persistence"],
        )

    def test_missing_service_source_still_refuses_an_incomplete_backup(self):
        (self.root / "infrastructure" / "identity").mkdir()
        with self.assertRaises(backup.BackupError):
            backup.configuration_sources(self.root)

    def test_neo4j_restore_builds_from_the_recovered_bundle_layout(self):
        for path in ("persistence/neo4j", "infrastructure/persistence/neo4j"):
            with self.subTest(layout=path):
                (self.root / path).mkdir(parents=True)
                with (
                    patch.object(restore, "ROOT", self.root),
                    patch.object(restore, "run") as run,
                ):
                    restore.start_recovered_neo4j(["docker", "compose"], ["fixture"])
                self.assertEqual(run.call_args_list[0].args[0][-1], path)
