"""Exercise the deployment archive, including host maintenance entry points."""

import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

ANSIBLE_DIR = Path(__file__).resolve().parents[2]


class SourceTransferTests(unittest.TestCase):
    def test_archive_contains_maintenance_without_private_or_generated_files(self):
        tasks = yaml.safe_load(
            (ANSIBLE_DIR / "tasks/deploy/source-transfer.yml").read_text()
        )
        arguments = next(
            task["ansible.builtin.command"]["argv"]
            for task in tasks[0]["block"]
            if "ansible.builtin.command" in task
        )
        included = [
            "compose.yaml",
            ".env.example",
            "infrastructure/monitoring/loki.yaml",
            "platform/app/src/app/main.py",
            "platform/ui/src/main.tsx",
            "scripts/up.sh",
            "tests/platform/harness.py",
            "operations/backup/scripts/backup-platform.py",
            "operations/maintenance/scripts/purge-project.py",
        ]
        excluded = [
            "infrastructure/monitoring/private/credentials",
            "platform/app/.venv/bin/python",
            "platform/ui/node_modules/package/index.js",
            "platform/app/.pytest_cache/state",
            "platform/.ruff_cache/state",
            "platform/.runtime/credentials",
            "platform/ui/dist/index.html",
            "platform/ui/test-results/report.json",
            "platform/ui/playwright-report/index.html",
            "platform/ui/.tmp/report.json",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            archive = Path(directory) / "source.tar.gz"
            for name in included + excluded:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            arguments = [
                str(archive)
                if argument == "{{ platform_archive.path }}"
                else str(root)
                if argument == "{{ platform_source_dir }}"
                else argument
                for argument in arguments
            ]
            subprocess.run(arguments, check=True, capture_output=True)
            with tarfile.open(archive) as packed:
                names = set(packed.getnames())
            self.assertTrue(set(included).issubset(names), set(included) - names)
            self.assertFalse(set(excluded) & names, set(excluded) & names)


if __name__ == "__main__":
    unittest.main()
