import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location(
    "restore", Path(__file__).parents[1] / "scripts/restore-recovery.py"
)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class RestoreRecoveryTests(unittest.TestCase):
    def test_preloaded_postgres_is_inspected_and_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "services": {
                    "postgres": {"image": "developer-platform-postgres:18.6-old"}
                }
            }
            with (
                patch.object(restore, "ROOT", root),
                patch.object(
                    restore, "run", side_effect=[json.dumps(source).encode(), b""]
                ) as run,
            ):
                restore.configure_compose(True)
            self.assertEqual(
                run.call_args_list[1].args[0],
                ["docker", "image", "inspect", "developer-platform-postgres:18.6-old"],
            )
            override = (root / "compose.override.yaml").read_text()
            self.assertIn("postgres:\n    build: !reset null", override)
            self.assertIn('GF_SMTP_ENABLED: "false"', override)

    def test_preloaded_candidate_image_replaces_source_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "services": {
                    "postgres": {"image": "developer-platform-postgres:18.6-old"}
                }
            }
            with (
                patch.object(restore, "ROOT", root),
                patch.object(
                    restore, "run", side_effect=[json.dumps(source).encode(), b""]
                ) as run,
            ):
                restore.configure_compose(
                    True, "developer-platform-postgres:18.6-extensions-20261112"
                )
            self.assertEqual(
                run.call_args_list[1].args[0],
                [
                    "docker",
                    "image",
                    "inspect",
                    "developer-platform-postgres:18.6-extensions-20261112",
                ],
            )
            self.assertIn(
                "image: developer-platform-postgres:18.6-extensions-20261112",
                (root / "compose.override.yaml").read_text(),
            )

    def test_candidate_image_requires_explicit_preload(self):
        with self.assertRaisesRegex(RuntimeError, "preloaded image"):
            restore.configure_compose(
                False, "developer-platform-postgres:18.6-extensions-20261112"
            )

    def test_retained_s3_archive_required_and_legacy_live_data_needs_pinned_release(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            path = bundle / "store-recovery.json"
            path.write_text(
                json.dumps(
                    {
                        "resources": [
                            {"provider": "s3", "state": "retired"},
                            {"provider": "neo4j", "state": "purged"},
                        ]
                    }
                )
            )
            with self.assertRaisesRegex(RuntimeError, "S3 volume is missing"):
                restore.store_volume_restore_targets(bundle)
            (bundle / "rustfs-data.tar.gz").write_bytes(b"synthetic archive identity")
            self.assertEqual(
                restore.store_volume_restore_targets(bundle),
                [("rustfs", "rustfs_data", "rustfs-data.tar.gz")],
            )
            path.write_text(
                json.dumps({"resources": [{"provider": "qdrant", "state": "active"}]})
            )
            with self.assertRaisesRegex(RuntimeError, "632b921"):
                restore.store_volume_restore_targets(bundle)

    def test_restored_access_is_quarantined_before_services_start(self):
        with patch.object(restore, "run") as run:
            restore.quarantine_hosted_access(["docker", "compose"])
        args = run.call_args
        self.assertIn("platform", args.args[0])
        self.assertIn("ON_ERROR_STOP=1", args.args[0])
        self.assertIn(b"recovery-required", args.kwargs["data"])
        self.assertIn(b"store_control", args.kwargs["data"])
        self.assertIn(b"expires_at=LEAST(expires_at,now())", args.kwargs["data"])
        self.assertIn(
            b"to_regclass", args.kwargs["data"]
        )  # Older bundles without hosted access remain supported.

    def test_latest_verified_intent_is_independent_of_selected_data_snapshot_and_checked(
        self,
    ):
        import hashlib

        intent = b'{"format":1,"resources":[]}'
        latest = {
            "id": "b" * 64,
            "time": "2026-10-17T12:00:00Z",
            "paths": ["/safe/bundle"],
        }
        older = {
            "id": "a" * 64,
            "time": "2026-10-16T12:00:00Z",
            "paths": ["/safe/bundle"],
        }
        manifest = {
            "sha256": {"store-recovery.json": hashlib.sha256(intent).hexdigest()}
        }
        with patch.object(
            restore,
            "run",
            side_effect=[
                json.dumps([latest, older]).encode(),
                json.dumps(manifest).encode(),
                intent,
            ],
        ) as run:
            self.assertEqual(restore.latest_store_intents(), intent)
        self.assertEqual(
            run.call_args_list[1].args[0][-2:], ["b" * 64, "/bundle/manifest.json"]
        )
        with (
            patch.object(
                restore,
                "run",
                side_effect=[
                    json.dumps([latest]).encode(),
                    json.dumps(manifest).encode(),
                    b"corrupt",
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "checksum mismatch"),
        ):
            restore.latest_store_intents()

    def test_only_known_bootstrap_duplicates_are_accepted(self):
        restore.check_import_errors(
            'ERROR:  role "postgres" already exists\nERROR:  database "platform" already exists\n'
        )
        warning = (
            "WARNING:  time_bucket function already exists, use duckdb.time_bucket "
            "instead. This is usually because the timescale extension is installed."
        )
        restore.check_import_errors(warning + "\n" + warning + "\n")
        restore.check_import_errors("")
        for message in [
            "ERROR: permission denied",
            'ERROR:  role "project_smoke" already exists',
            "WARNING: something unexpected",
            'ERROR:  role "postgres" already exists\nERROR:  role "postgres" already exists',
        ]:
            with self.assertRaises(RuntimeError):
                restore.check_import_errors(message)

    def test_project_secrets_are_restored_through_stdin_and_pods_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "project-secrets.json").write_text(
                json.dumps(
                    {
                        "format": 1,
                        "projects": {
                            "smoke": {
                                "data": {"API_KEY": "dmFsdWU="},
                                "annotations": {
                                    "platform.example/changed-API_KEY": "t"
                                },
                            }
                        },
                    }
                )
            )
            with patch.object(restore, "run") as run:
                self.assertTrue(restore.restore_project_secrets(bundle, "smoke"))
                self.assertFalse(restore.restore_project_secrets(bundle, "other"))
            apply, restart = run.call_args_list
            self.assertNotIn("dmFsdWU=", " ".join(apply.args[0]))
            body = json.loads(apply.kwargs["data"])
            self.assertEqual(
                (body["metadata"]["namespace"], body["data"]),
                ("project-smoke", {"API_KEY": "dmFsdWU="}),
            )
            self.assertEqual(
                restart.args[0][-3:], ["rollout", "restart", "deployment/smoke"]
            )
            (bundle / "project-secrets.json").unlink()
            self.assertFalse(restore.restore_project_secrets(bundle, "smoke"))

    def test_archive_cannot_escape_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.mkdir()
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                member = tarfile.TarInfo("../outside")
                member.size = 1
                out.addfile(member, io.BytesIO(b"x"))
            with self.assertRaises(tarfile.FilterError):
                restore.extract(archive, target)
            self.assertFalse((root / "outside").exists())

    def test_legacy_virtualenv_symlink_is_skipped_but_sources_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "legacy.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                source_dir = tarfile.TarInfo("platform/app/src/app")
                source_dir.type = tarfile.DIRTYPE
                source_dir.mode = 0o755
                output.addfile(source_dir)

                secret_dir = tarfile.TarInfo(".runtime/stores")
                secret_dir.type = tarfile.DIRTYPE
                secret_dir.mode = 0o700
                output.addfile(secret_dir)

                interpreter = tarfile.TarInfo("platform/.venv/bin/python")
                interpreter.type = tarfile.SYMTYPE
                interpreter.linkname = "/usr/bin/python3"
                output.addfile(interpreter)

                content = b"services: {}\n"
                compose = tarfile.TarInfo("infrastructure/proxy/compose.yaml")
                compose.size = len(content)
                output.addfile(compose, io.BytesIO(content))

            target = root / "restored"
            target.mkdir()
            restore.extract(archive, target)
            self.assertFalse((target / "platform/.venv").exists())
            self.assertEqual(
                (target / "platform/app/src/app").stat().st_mode & 0o777, 0o755
            )
            self.assertEqual((target / ".runtime/stores").stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (target / "infrastructure/proxy/compose.yaml").read_bytes(), content
            )

    def test_legacy_bundle_requires_matching_staged_environment_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "platform"
            target.mkdir()
            bundle = root / "recovery" / "bundle"
            bundle.mkdir(parents=True)
            with patch.object(restore, "ROOT", target):
                with self.assertRaisesRegex(RuntimeError, "matching .env.example"):
                    restore.ensure_environment_example(bundle)

                (bundle.parent / "env.example").write_text("EXAMPLE=default\n")
                restore.ensure_environment_example(bundle)
                self.assertEqual(
                    (target / ".env.example").read_text(), "EXAMPLE=default\n"
                )
