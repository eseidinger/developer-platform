import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('recovery_vm', Path(__file__).parents[1] / 'scripts/recovery-vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class RecoveryVMTests(unittest.TestCase):
    def setUp(self):
        # These unit tests mock execution/downloads; installed VM tools are irrelevant.
        tools = patch.object(vm.shutil, 'which', side_effect=lambda name: '/mock/bin/' + name)
        tools.start()
        self.addCleanup(tools.stop)

    def test_missing_tool_fails_before_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(vm.shutil, 'which', return_value=None), \
                 patch.object(vm, 'download') as download:
                with self.assertRaisesRegex(RuntimeError, 'Missing required tool'):
                    vm.create(SimpleNamespace(), Path(tmp) / 'vm')
                download.assert_not_called()

    def test_existing_vm_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk = Path(tmp) / 'disk.qcow2'
            disk.write_bytes(b'recovery data')
            with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
                vm.create(SimpleNamespace(), Path(tmp))
            self.assertEqual(disk.read_bytes(), b'recovery data')

    def test_checksum_failure_does_not_publish_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / 'key.pub'
            key.write_text('ssh-ed25519 test-key')
            def download(url, target):
                target.write_bytes((('0' * 64 + ' *' + vm.IMAGE + '\n').encode())
                                   if url.endswith('SHA256SUMS') else b'corrupt image')
            with patch.object(vm, 'download', side_effect=download), patch.object(vm, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    vm.create(SimpleNamespace(public_key=key, disk_gb=100), root / 'vm')
            self.assertFalse((root / 'vm').exists())
            self.assertEqual(len(list(root.iterdir())), 1)
            self.assertEqual(run.call_count, 1)  # Only public-key validation; no image conversion.

    def test_private_key_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / 'key'
            key.write_text('-----BEGIN OPENSSH PRIVATE KEY-----')
            with patch.object(vm, 'download') as download:
                with self.assertRaisesRegex(RuntimeError, 'public key'):
                    vm.create(SimpleNamespace(public_key=key), root / 'vm')
                download.assert_not_called()
