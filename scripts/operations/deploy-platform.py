#!/usr/bin/env python3
"""Perform the explicit controlled deployment used locally and by Ansible."""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Prefer the same project-local tools as up.sh, including when run by Ansible.
ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = Path("/run/systemd/system")
MAINTENANCE_UNITS = (
    "platform-backup.service",
    "platform-backup-freshness-drill.service",
    "backup-drill-*",
    "platform-availability-*",
)


class DeploymentError(RuntimeError):
    """A deployment failure described without forwarding private tool output."""


def command(arguments, *, private=False):
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE if private else None,
        stderr=subprocess.PIPE if private else None,
        text=True,
    )
    if result.returncode:
        raise DeploymentError(
            "Deployment step failed; inspect private host diagnostics"
        )
    return result.stdout or ""


def preflight():
    # Fail before stopping anything. --check validates configuration without writes.
    command(
        [sys.executable, "scripts/setup/configure-platform.py", "--runtime", "--check"]
    )
    if SYSTEMD.is_dir():
        active = command(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--state=activating,active,running",
                "--no-legend",
                *MAINTENANCE_UNITS,
            ],
            private=True,
        )
        if active.strip():
            raise DeploymentError(
                "Deployment cannot overlap active backup or availability maintenance"
            )
    command(["docker", "compose", "--profile", "*", "config", "--quiet"], private=True)
    command(
        [
            sys.executable,
            "scripts/checks/check-network-addresses.py",
            "--validate-networks",
        ]
    )
    command(["mountpoint", "-q", "/var/lib/developer-platform/tempo"], private=True)
    # up.sh checks these too. Check early so missing tools cannot cause an outage.

    for tool in ("docker", "k3d", "kubectl", "python3", "setfacl"):
        if shutil.which(tool) is None:
            raise DeploymentError("Missing deployment prerequisite: " + tool)


def wait_for_api(timeout):
    deadline = time.monotonic() + timeout
    # Loopback readiness must not be sent through an operator HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while True:
        try:
            with opener.open("http://127.0.0.1:8000/readyz", timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeploymentError("Platform API readiness timed out")
        time.sleep(min(5, remaining))


def deploy(*, check=False, readiness_timeout=300):
    preflight()
    if check:
        print("Deployment preflight passed; no services were stopped.")
        return

    # Generate and verify selected-store configuration before the service outage.
    command([sys.executable, "scripts/setup/configure-platform.py", "--runtime"])
    command([sys.executable, "scripts/setup/prepare-stores.py"], private=True)
    print(
        "Stopping and recreating Compose containers; persistent data and k3d are retained.",
        flush=True,
    )
    command(["docker", "compose", "stop", "--timeout", "60"])
    command(["docker", "compose", "rm", "--force"])
    # Never use compose down: the workload cluster retains the shared network.
    command(["bash", "scripts/up.sh"])
    wait_for_api(readiness_timeout)
    print("Platform deployment completed and API dependencies are ready.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Run non-mutating preflight checks only"
    )
    parser.add_argument(
        "--readiness-timeout",
        type=int,
        default=300,
        help="API readiness budget in seconds (5–3600)",
    )
    args = parser.parse_args()
    if not 5 <= args.readiness_timeout <= 3600:
        parser.error("readiness timeout must be between 5 and 3600 seconds")
    os.environ["PATH"] = (
        str(ROOT / ".runtime/bin") + os.pathsep + os.environ.get("PATH", "")
    )
    try:
        deploy(check=args.check, readiness_timeout=args.readiness_timeout)
    except (DeploymentError, OSError) as error:
        # OSErrors may embed private paths; don't forward arbitrary command errors.
        message = (
            str(error)
            if isinstance(error, DeploymentError)
            else "Deployment tool unavailable"
        )
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
