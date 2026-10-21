"""Local trust setup fails closed and preserves previously trusted certificates."""

import importlib.util
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "prepare_local_trust", ROOT / "scripts/setup/prepare-local-trust.py"
)
trust = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trust)


class LocalTrustTests(unittest.TestCase):
    def test_workload_bundle_preserves_system_roots_and_contains_only_public_certificates(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "IDENTITY_DOMAIN=identity.localhost\nLOCAL_APPLICATION_HTTPS_ENABLED=true\n"
            )
            roots = ssl.create_default_context().get_ca_certs(binary_form=True)
            public = [ssl.DER_cert_to_PEM_cert(der) for der in roots[:2]]
            with patch.object(
                trust, "public_certificate", side_effect=public
            ) as export:
                trust.prepare(root)
            self.assertEqual(
                [call.args[1] for call in export.call_args_list],
                ["proxy", "local-application-edge"],
            )
            target = root / ".runtime/trust/application-ca-bundle.pem"
            bundle = target.read_text()
            self.assertTrue(all(certificate in bundle for certificate in public))
            self.assertNotIn("PRIVATE KEY", bundle)
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)
            self.assertGreaterEqual(
                len(ssl.create_default_context(cadata=bundle).get_ca_certs()),
                len(roots),
            )

    def test_public_identity_uses_system_roots_without_contacting_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("IDENTITY_DOMAIN=identity.example.com\n")
            with patch.object(trust.subprocess, "run") as run:
                trust.prepare(root)
            run.assert_not_called()
            self.assertTrue((root / ".runtime/trust").is_dir())
            self.assertFalse((root / ".runtime/trust/local-ca.pem").exists())

    def test_invalid_export_never_replaces_the_previously_trusted_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("IDENTITY_DOMAIN=identity.localhost\n")
            target = root / ".runtime/trust/local-ca.pem"
            target.parent.mkdir(parents=True)
            target.write_text("previous-public-certificate")
            with (
                patch.object(
                    trust.subprocess,
                    "run",
                    return_value=Mock(returncode=0, stdout="not a certificate"),
                ),
                self.assertRaises(ssl.SSLError),
            ):
                trust.prepare(root)
            self.assertEqual(target.read_text(), "previous-public-certificate")

    def test_symlinked_trust_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("IDENTITY_DOMAIN=identity.localhost\n")
            (root / ".runtime").mkdir()
            (root / "outside").mkdir()
            (root / ".runtime/trust").symlink_to(root / "outside")
            with self.assertRaisesRegex(ValueError, "symlink"):
                trust.prepare(root)
            self.assertEqual(list((root / "outside").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
