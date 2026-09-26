#!/usr/bin/env python3
"""Create and run an isolated Ubuntu recovery guest using QEMU/KVM in WSL 2."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import tempfile
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[3]
IMAGE = 'ubuntu-24.04-server-cloudimg-amd64.img'
BASE = 'https://cloud-images.ubuntu.com/releases/noble/release/'


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def download(url, target):
    with urllib.request.urlopen(url, timeout=60) as source, target.open('wb') as output:
        shutil.copyfileobj(source, output)


def cloud_config(key):
    return {'hostname': 'platform-recovery', 'manage_etc_hosts': True,
            'ssh_pwauth': False, 'disable_root': True,
            'users': [{'name': 'recovery', 'groups': ['sudo'], 'shell': '/bin/bash',
                       'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'lock_passwd': True,
                       'ssh_authorized_keys': [key]}]}


def create(args, directory):
    if directory.exists():
        raise RuntimeError('VM directory already exists; refusing to overwrite recovery data')
    for tool in ['ssh-keygen', 'qemu-img', 'cloud-localds']:
        if shutil.which(tool) is None:
            raise RuntimeError(f'Missing required tool: {tool}')
    key_path = args.public_key.expanduser().resolve()
    key = key_path.read_text().strip()
    if '\n' in key or not key.startswith(('ssh-ed25519 ', 'ssh-rsa ', 'ecdsa-sha2-')):
        raise RuntimeError('Supply a single OpenSSH public key, not a private key')
    run('ssh-keygen', '-l', '-f', key_path)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.recovery-vm-', dir=directory.parent) as tmp:
        work = Path(tmp)
        print('Downloading Ubuntu image and SHA256SUMS over HTTPS...', flush=True)
        download(BASE + 'SHA256SUMS', work / 'SHA256SUMS')
        matches = [line.split()[0] for line in (work / 'SHA256SUMS').read_text().splitlines()
                   if len(line.split()) == 2 and line.split()[1].lstrip('*') == IMAGE]
        if len(matches) != 1:
            raise RuntimeError('Image checksum missing or ambiguous')
        download(BASE + IMAGE, work / 'base.img')
        with (work / 'base.img').open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != matches[0]:
            raise RuntimeError('Ubuntu image checksum mismatch; retry if the release changed')
        run('qemu-img', 'convert', '-f', 'qcow2', '-O', 'qcow2', work / 'base.img', work / 'disk.qcow2')
        run('qemu-img', 'resize', work / 'disk.qcow2', f'{args.disk_gb}G')
        (work / 'base.img').unlink()
        # JSON is a YAML subset; cloud-init consumes it after the cloud-config header.
        (work / 'user-data').write_text('#cloud-config\n' + json.dumps(cloud_config(key), indent=2) + '\n')
        (work / 'meta-data').write_text(json.dumps({'instance-id': str(uuid.uuid4()),
                                                   'local-hostname': 'platform-recovery'}))
        run('cloud-localds', work / 'seed.img', work / 'user-data', work / 'meta-data')
        (work / 'image.json').write_text(json.dumps({'url': BASE + IMAGE, 'sha256': digest}, indent=2) + '\n')
        os.rename(work, directory)
    print(f'Created {directory}. Start the VM in a dedicated terminal with the start command.')


def qemu_command(directory, args):
    return ['qemu-system-x86_64', '-name', 'platform-recovery', '-accel', 'kvm',
            '-cpu', 'host', '-smp', str(args.cpus), '-m', str(args.memory_mb),
            '-drive', 'file=disk.qcow2,format=qcow2,if=virtio',
            '-drive', 'file=seed.img,format=raw,if=virtio,readonly=on',
            '-nic', f'user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:{args.ssh_port}-:22',
            '-display', 'none', '-serial', 'file:console.log', '-monitor', 'none',
            '-qmp', 'unix:qmp.sock,server=on,wait=off', '-no-reboot']


def stop(directory):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(10)
        client.connect(str(directory / 'qmp.sock'))
        with client.makefile('rwb') as stream:
            json.loads(stream.readline())  # QMP greeting
            for command in ['qmp_capabilities', 'system_powerdown']:
                stream.write(json.dumps({'execute': command}).encode() + b'\n')
                stream.flush()
                while True:
                    response = json.loads(stream.readline())
                    if 'error' in response:
                        raise RuntimeError(str(response['error']))
                    if 'return' in response:
                        break
    print('Graceful shutdown requested; wait for the QEMU terminal to exit.')


def positive(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'start', 'stop'])
    parser.add_argument('--directory', type=Path, default=ROOT / '.runtime/recovery-vm')
    parser.add_argument('--public-key', type=Path, default=Path('~/.ssh/id_ed25519.pub'))
    parser.add_argument('--disk-gb', type=positive, default=100)
    parser.add_argument('--cpus', type=positive, default=4)
    parser.add_argument('--memory-mb', type=positive, default=8192)
    parser.add_argument('--ssh-port', type=positive, default=2222)
    args = parser.parse_args()
    if args.ssh_port > 65535:
        parser.error('SSH port must be at most 65535')
    os.umask(0o077)
    directory = args.directory.expanduser().resolve()
    try:
        if args.action == 'create':
            create(args, directory)
        elif args.action == 'stop':
            stop(directory)
        else:
            if platform.machine() != 'x86_64' or not os.access('/dev/kvm', os.R_OK | os.W_OK):
                raise RuntimeError('Requires x86_64 WSL/Linux with accessible /dev/kvm')
            for name in ['disk.qcow2', 'seed.img', 'image.json']:
                if not (directory / name).is_file():
                    raise RuntimeError('Create the VM first; required files are missing')
            with (directory / 'run.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                print(f'VM running in this terminal. SSH: recovery@127.0.0.1 port {args.ssh_port}', flush=True)
                print(f'Console: {directory / "console.log"}. Use stop from another terminal.', flush=True)
                subprocess.run(qemu_command(directory, args), cwd=directory, check=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        parser.exit(1, f'Recovery VM: {error}\n')


if __name__ == '__main__':
    main()
