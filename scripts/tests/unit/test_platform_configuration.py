"""Shared configuration contracts, exercised only in disposable checkouts."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.internal.deployment_options import ConfigurationError
from scripts.internal.env import parse_environment
from scripts.internal.platform_configuration import configure, render_settings

ROOT = Path(__file__).resolve().parents[3]


class PlatformConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tempo = self.root / "infrastructure/monitoring/tempo.yaml"
        self.tempo.parent.mkdir(parents=True)
        self.tempo.write_text(
            (ROOT / "infrastructure/monitoring/tempo.yaml").read_text()
        )
        self.environment = self.root / ".env"
        defaults = (ROOT / ".env.example").read_text()
        (self.root / ".env.example").write_text(defaults)
        self.environment.write_text(
            defaults.replace("DATABASE_KEY=\n", "DATABASE_KEY=fixture-secret\n")
        )
        self.environment.chmod(0o600)

    def test_inventory_options_render_into_valid_local_settings(self):
        spec = importlib.util.spec_from_file_location(
            "inventory_adapter", ROOT / "ansible/filter_plugins/platform_inventory.py"
        )
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        options = {
            "stores": {
                "profiles": ["qdrant"],
                "capacity_bytes": {"postgresql": 4096, "qdrant": 2048},
            },
            "network": {"subnet": "10.55.8.0/24"},
            "search_console_network": {"subnet": "10.55.9.0/29"},
        }
        specification = {
            "environment": {"PLATFORM_DOMAIN": "platform.fixture.example"},
            "options": options,
            "tracing": {"sample_rate": 0.25, "retention": "168h"},
        }
        rendered = render_settings(specification)
        self.assertEqual(
            {key: rendered[key] for key in plugin.platform_inventory_settings(options)},
            plugin.platform_inventory_settings(options),
        )
        self.assertTrue(configure(self.root, specification))
        result = parse_environment(self.environment.read_text())
        for key, value in rendered.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result["DATABASE_KEY"], "fixture-secret")
        self.assertIn("    block_retention: 168h\n", self.tempo.read_text())
        self.assertFalse(configure(self.root, specification))

    def test_omissions_preserve_custom_settings_comments_and_secrets(self):
        content = self.environment.read_text().replace(
            "COMPOSE_PROFILES=", "COMPOSE_PROFILES=qdrant"
        )
        content = content.replace(
            'STORE_CAPACITY_BYTES={"postgresql":17179869184}',
            'STORE_CAPACITY_BYTES={"postgresql":100,"qdrant":200}',
        )
        self.environment.write_text(
            content + "# retained operator setting\nCUSTOM_SETTING=value\n"
        )
        before = self.environment.read_bytes()
        self.assertFalse(configure(self.root, {}))
        self.assertEqual(self.environment.read_bytes(), before)
        configure(
            self.root, {"environment": {"PLATFORM_DOMAIN": "new.fixture.example"}}
        )
        after = self.environment.read_text()
        self.assertIn("COMPOSE_PROFILES=qdrant\n", after)
        self.assertIn("# retained operator setting\nCUSTOM_SETTING=value\n", after)
        self.assertIn("DATABASE_KEY=fixture-secret\n", after)
        self.assertEqual(self.environment.stat().st_mode & 0o777, 0o600)

    def test_check_mode_does_not_change_any_configuration(self):
        before = (self.environment.read_bytes(), self.tempo.read_bytes())
        self.assertTrue(
            configure(self.root, {"tracing": {"retention": "168h"}}, check=True)
        )
        self.assertEqual(
            (self.environment.read_bytes(), self.tempo.read_bytes()), before
        )

    def test_private_mode_is_enforced_without_rewriting_secrets(self):
        self.environment.chmod(0o644)
        original = self.environment.read_bytes()
        self.assertTrue(configure(self.root, {}, check=True))
        self.assertEqual(self.environment.stat().st_mode & 0o777, 0o644)
        self.assertTrue(configure(self.root, {}))
        self.assertEqual(self.environment.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.environment.read_bytes(), original)

    def test_invalid_settings_never_partially_update_files(self):
        before = (self.environment.read_bytes(), self.tempo.read_bytes())
        for specification in [
            {"environment": {"DATABASE_KEY": "must-not-be-accepted"}},
            {"environment": {"PLATFORM_DOMAIN": "bad\nSECRET=leak"}},
            {"environment": {"CAPACITY_RESERVE_MEMORY_MIB": "invalid"}},
            {"environment": {"CAPACITY_ADMISSION_ENABLED": "sometimes"}},
            {"environment": {"ALLOWED_EGRESS_PORTS": "443;anything"}},
            {
                "options": {
                    "stores": {
                        "profiles": ["neo4j"],
                        "capacity_bytes": {"postgresql": 1},
                    }
                }
            },
            {"options": {"search_console_network": {"subnet": "172.30.80.0/29"}}},
            {"tracing": {"sample_rate": "NaN"}},
            {"tracing": {"retention": "0h"}},
        ]:
            with (
                self.subTest(specification=specification),
                self.assertRaises(ConfigurationError),
            ):
                configure(self.root, specification)
            self.assertEqual(
                (self.environment.read_bytes(), self.tempo.read_bytes()), before
            )

    def test_runtime_checks_honor_overrides_but_configuration_application_ignores_them(
        self,
    ):
        with patch.dict(os.environ, {"PLATFORM_TRACE_SAMPLE_RATE": "invalid"}):
            with self.assertRaises(ConfigurationError):
                configure(self.root, {}, check=True, runtime=True)
            self.assertFalse(configure(self.root, {}, check=True))

    def test_cli_works_with_only_standard_library_and_from_another_directory(self):
        # Model exactly the source subset transferred by the deployment playbook.
        for relative in (
            "scripts/setup/configure-platform.py",
            "scripts/internal/deployment_options.py",
            "scripts/internal/platform_configuration.py",
            "scripts/internal/env.py",
            "scripts/internal/__init__.py",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                str(self.root / "scripts/setup/configure-platform.py"),
                "--stdin",
            ],
            input=json.dumps({"tracing": {"retention": "48h"}}),
            cwd="/tmp",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Platform configuration updated.\n")
        self.assertNotIn("fixture-secret", result.stdout + result.stderr)
        self.assertIn("    block_retention: 48h\n", self.tempo.read_text())

        # Local operators edit .env directly, then validate without another file.
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                str(self.root / "scripts/setup/configure-platform.py"),
                "--check",
            ],
            cwd="/tmp",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Platform configuration validated.\n")


if __name__ == "__main__":
    unittest.main()
