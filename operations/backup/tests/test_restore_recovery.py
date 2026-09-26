import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('restore', Path(__file__).parents[1] / 'scripts/restore-recovery.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class RestoreRecoveryTests(unittest.TestCase):
    def test_only_known_bootstrap_duplicates_are_accepted(self):
        restore.check_import_errors('ERROR:  role "postgres" already exists\nERROR:  database "platform" already exists\n')
        restore.check_import_errors('')
        for message in ['ERROR: permission denied', 'ERROR:  role "project_smoke" already exists',
                        'WARNING: something unexpected',
                        'ERROR:  role "postgres" already exists\nERROR:  role "postgres" already exists']:
            with self.assertRaises(RuntimeError):
                restore.check_import_errors(message)

    def test_archive_cannot_escape_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'target'
            target.mkdir()
            archive = root / 'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as out:
                member = tarfile.TarInfo('../outside')
                member.size = 1
                out.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(tarfile.FilterError):
                restore.extract(archive, target)
            self.assertFalse((root / 'outside').exists())
