"""Exercise storage bootstrap with host commands mocked; never mount filesystems."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class TempoStorageTests(unittest.TestCase):
    def test_existing_image_is_preserved_and_boot_dependency_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "storage"
            base.mkdir()
            image = base / "tempo-4g.img"
            image.write_bytes(b"retained trace filesystem")
            units = root / "units"
            units.mkdir()
            commands = root / "bin"
            commands.mkdir()
            log = root / "commands.log"
            mock = commands / "mock"
            mock.write_text(
                "#!/bin/bash\n"
                'printf "%s\\n" "${0##*/} $*" >> "$COMMAND_LOG"\n'
                'case "${0##*/}" in\n'
                "  id) echo 0 ;;\n"
                "  findmnt) echo /dev/loop7 ;;\n"
                "  systemd-escape) echo var-lib-developer\\\\x2dplatform-tempo.mount ;;\n"
                "  truncate|mkfs.ext4|mount) exit 99 ;;\n"
                "esac\n"
            )
            mock.chmod(0o755)
            for name in (
                "id",
                "findmnt",
                "mountpoint",
                "chown",
                "systemd-escape",
                "systemctl",
                "truncate",
                "mkfs.ext4",
                "mount",
            ):
                (commands / name).symlink_to(mock)
            source = (ROOT / "scripts/setup/prepare-tempo-storage.sh").read_text()
            source = source.replace("/var/lib/developer-platform", str(base))
            source = source.replace("/etc/systemd/system", str(units))
            source = source.replace("/run/systemd/system", str(units))
            script = root / "prepare.sh"
            script.write_text(source)
            environment = {
                **os.environ,
                "PATH": f"{commands}:{os.environ['PATH']}",
                "COMMAND_LOG": str(log),
            }
            for _ in range(2):
                subprocess.run(
                    ["bash", str(script)],
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(image.read_bytes(), b"retained trace filesystem")
            mount_units = list(units.glob("*.mount"))
            self.assertEqual(len(mount_units), 1)
            unit = mount_units[0].read_text()
            self.assertIn(f"What={image}\n", unit)
            self.assertIn(f"Where={base}/tempo\n", unit)
            self.assertIn("Options=loop,nodev,nosuid,noexec\n", unit)
            self.assertIn("WantedBy=local-fs.target\n", unit)
            dependency = (units / "docker.service.d/tempo-storage.conf").read_text()
            self.assertIn(f"RequiresMountsFor={base}/tempo\n", dependency)
            calls = log.read_text()
            self.assertEqual(calls.count("systemctl daemon-reload\n"), 2)
            self.assertEqual(calls.count("systemctl enable "), 2)
            self.assertNotIn("systemctl restart", calls)


if __name__ == "__main__":
    unittest.main()
