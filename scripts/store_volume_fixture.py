"""Stopped-volume capture/empty-volume restore for temporary provider containers.

Uses Docker-owned fixture volumes, never production paths or a host mount. The
helper has no network and mounts only the explicit fixture volume. No archive
contents, provider logs or credentials are printed.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

HELPER = 'rustfs/rustfs:1.0.2@sha256:7e948dad4748bda48f8985fda7195f8cf2e4259427011f6120acc2c9acf51587'


def run(arguments, **kwargs):
    result = subprocess.run(arguments, stderr=subprocess.PIPE, timeout=90, **kwargs)
    if result.returncode:
        raise RuntimeError('Disposable store-volume recovery failed')


@contextmanager
def restored(source_container, source_volume, destination, image, arguments, env):
    identity = uuid4().hex[:12]
    name, volume = 'restored-store-' + identity, 'restored-store-data-' + identity
    helper = ['docker', 'run', '--rm', '--network', 'none', '--memory', '128m', '--cpus', '1', '--user', '0:0']
    with tempfile.TemporaryDirectory(prefix='store-volume-recovery-') as directory:
        archive = Path(directory) / 'data.tar.gz'
        try:
            run(['docker', 'stop', '--time', '30', source_container], stdout=subprocess.DEVNULL)
            try:
                descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'wb') as stream:
                    run([*helper, '--mount', f'type=volume,src={source_volume},dst=/capture,readonly',
                        '--entrypoint', 'tar', HELPER, '-czf', '-', '-C', '/capture', '.'], stdout=stream)
            finally:
                run(['docker', 'start', source_container], stdout=subprocess.DEVNULL)
            run(['docker', 'volume', 'create', volume], stdout=subprocess.DEVNULL)
            with archive.open('rb') as stream:
                run([*helper, '-i', '--mount', f'type=volume,src={volume},dst=/restore',
                    '--entrypoint', 'tar', HELPER, '-xzf', '-', '-C', '/restore'], stdin=stream, stdout=subprocess.DEVNULL)
            run(['docker', 'run', '-d', '--name', name, '--mount',
                f'type=volume,src={volume},dst={destination}', *arguments, image], env=env, stdout=subprocess.DEVNULL)
            yield name
        finally:
            subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)
            subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)
