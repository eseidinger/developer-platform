"""Initialization repairs blank credentials without rotating live secrets."""

import tempfile
import unittest
from pathlib import Path

from scripts.init import initialize


class InitializationTests(unittest.TestCase):
    def test_blank_assignments_are_filled_and_existing_secrets_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".env"
            path.write_text(
                "# Preserve this comment\nPOSTGRES_PASSWORD=\nDATABASE_KEY=existing-secret\nCOMPOSE_PROFILES=s3,qdrant\n"
            )
            changed = initialize(root)
            self.assertIn("POSTGRES_PASSWORD", changed)
            self.assertNotIn("DATABASE_KEY", changed)
            content = path.read_text()
            self.assertNotIn("POSTGRES_PASSWORD=\n", content)
            self.assertIn("DATABASE_KEY=existing-secret\n", content)
            self.assertIn("# Preserve this comment\n", content)
            self.assertIn("COMPOSE_PROFILES=s3,qdrant\n", content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(initialize(root), [])
            self.assertEqual(path.read_text(), content)

    def test_template_creates_private_credentials_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text(
                "POSTGRES_PASSWORD=\nPLATFORM_DOMAIN=platform.localhost\n"
            )
            initialize(root)
            self.assertEqual((root / ".runtime").stat().st_mode & 0o777, 0o700)
            self.assertIn(
                "PLATFORM_DOMAIN=platform.localhost\n", (root / ".env").read_text()
            )

    def test_symlink_is_not_used_as_a_configuration_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            original.write_text("unchanged")
            (root / ".env").symlink_to(original)
            with self.assertRaises(ValueError):
                initialize(root)
            self.assertEqual(original.read_text(), "unchanged")
