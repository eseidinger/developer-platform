"""Open a local TCP forward for an active named-store credential."""

from __future__ import annotations

import ipaddress
import re
import stat
import subprocess
from pathlib import Path

from .config import ConfigurationError


def _file(path: str, *, private: bool) -> Path:
    try:
        selected = Path(path).expanduser().resolve(strict=True)
        mode = selected.stat().st_mode
    except OSError:
        raise ConfigurationError(
            "The SSH identity or known-hosts file does not exist or is unreadable."
        ) from None
    if not stat.S_ISREG(mode):
        raise ConfigurationError("SSH key and known-hosts paths must be regular files.")
    if private and mode & 0o077:
        raise ConfigurationError(
            "The SSH identity file must be readable only by its owner."
        )
    return selected


def _port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigurationError("The platform returned an invalid SSH port.")
    return value


def ssh_command(
    credential: dict, identity_file: str, known_hosts: str, local_port: int
) -> list[str]:
    """Build an SSH command using only validated server connection details."""
    if credential.get("state") != "active":
        raise ConfigurationError(
            "The credential is not active; inspect it again after issuance completes."
        )
    if credential.get("provider") not in {
        "postgresql",
        "s3",
        "qdrant",
        "opensearch",
        "neo4j",
    }:
        raise ConfigurationError("The credential has an unsupported store provider.")
    ssh = credential.get("ssh")
    if not isinstance(ssh, dict):
        raise ConfigurationError(
            "No reachable SSH bastion is configured for this credential."
        )
    if ssh.get("user") != "platform-db":
        raise ConfigurationError("The platform returned an unexpected SSH user.")
    host = ssh.get("host")
    if not isinstance(host, str) or not host or len(host) > 253:
        raise ConfigurationError("The platform returned an invalid SSH host.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
            raise ConfigurationError(
                "The platform returned an invalid SSH host."
            ) from None
    destination = ssh.get("destination")
    try:
        if not isinstance(destination, str):
            raise ValueError()
        ipaddress.ip_address(destination)
    except ValueError:
        raise ConfigurationError(
            "The platform returned an invalid relay address."
        ) from None
    remote_port = _port(ssh.get("destination_port"))
    ssh_port = _port(ssh.get("port"))
    if (
        not isinstance(local_port, int)
        or isinstance(local_port, bool)
        or not 1 <= local_port <= 65535
    ):
        raise ConfigurationError("Choose a local TCP port from 1 to 65535.")
    key = _file(identity_file, private=True)
    hosts = _file(known_hosts, private=False)
    destination_address = f"[{destination}]" if ":" in destination else destination
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-N",
        "-T",
        "-i",
        str(key),
        "-p",
        str(ssh_port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(hosts),
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ConnectTimeout=5",
        "-L",
        f"127.0.0.1:{local_port}:{destination_address}:{remote_port}",
        "platform-db@" + host,
    ]


def run_tunnel(command: list[str]) -> int:
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        raise ConfigurationError(
            "OpenSSH 'ssh' is required to open a store tunnel."
        ) from None
