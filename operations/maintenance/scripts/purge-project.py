#!/usr/bin/env python3
"""Finish confirmed project purges on the platform host. Run as root via systemd.

Only the API's durable purge ledger authorizes work. All identifiers are read
back from that ledger; no caller can supply arbitrary filesystem paths or shell
commands. Docker and backup credentials stay outside the public API container.
"""

import argparse
import fcntl
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import UUID


class MaintenanceError(Exception):
    pass


def command(args, root, allow_pending=False):
    result = subprocess.run(
        args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
    )
    if result.returncode and not (allow_pending and result.returncode == 3):
        raise MaintenanceError("Maintenance command failed")
    return None if result.returncode else result.stdout


def api(root, action, identity, allow_pending=False):
    return command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "platform-api",
            "python",
            "-m",
            "app.lifecycle.maintenance",
            action,
            str(UUID(identity)),
        ],
        root,
        allow_pending,
    )


def remove_tenant(
    root, tenant, storage=Path("/var/lib/developer-platform/tempo"), service="tempo"
):
    tenant = str(UUID(tenant))
    if service not in {"tempo", "loki"}:
        raise MaintenanceError("Unsupported telemetry storage")
    # A symlink could redirect privileged cleanup outside the configured store.
    if storage.is_symlink() or not storage.is_dir():
        raise MaintenanceError("Tempo storage directory is unavailable")
    command(["docker", "compose", "stop", service], root)
    try:
        matches = sorted(
            (p for p in storage.rglob("*") if tenant in p.name),
            key=lambda p: len(p.parts),
        )
        for path in matches:
            if any(
                parent.is_symlink()
                for parent in (path, *path.parents)
                if parent != storage.parent
            ):
                raise MaintenanceError("Unexpected symlink in trace storage")
            if not path.exists():
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        if any(tenant in str(p.relative_to(storage)) for p in storage.rglob("*")):
            raise MaintenanceError("Project trace files remain")
    finally:
        command(["docker", "compose", "start", service], root)


def remove_workload_logs(root, project):
    if not re.fullmatch(r"[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?", project):
        raise MaintenanceError("Invalid project name")
    nodes = (
        command(
            [
                "docker",
                "ps",
                "--format",
                "{{.Names}}",
                "--filter",
                "name=k3d-workloads-",
            ],
            root,
        )
        .decode()
        .splitlines()
    )
    for node in nodes:
        for directory, pattern in (
            ("/var/log/pods", "project-" + project + "_*"),
            ("/var/log/containers", "*_project-" + project + "_*"),
        ):
            paths = (
                command(
                    [
                        "docker",
                        "exec",
                        node,
                        "find",
                        directory,
                        "-maxdepth",
                        "1",
                        "-name",
                        pattern,
                    ],
                    root,
                )
                .decode()
                .splitlines()
            )
            for path in paths:
                if Path(path).parent != Path(directory):
                    raise MaintenanceError("Unexpected workload log path")
                command(["docker", "exec", node, "rm", "-rf", "--", path], root)


def clean_backups(root, identity, backup_config):
    spec = importlib.util.spec_from_file_location(
        "maintenance_backup", root / "operations/backup/scripts/backup-platform.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    job = module.Job(json.loads(backup_config.read_text()))
    with (job.state / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # A fresh verified full backup preserves the remaining projects before
        # snapshots containing the deleted project are forgotten and pruned.
        job.run()
        status = job.read("status.json", {})
        if status.get("running") or not status.get("last_verified_snapshot"):
            raise MaintenanceError("No verified clean backup")
        clean = status["last_verified_snapshot"]
        snapshots = json.loads(
            job.command(
                [
                    job.restic,
                    "snapshots",
                    "--json",
                    "--host",
                    job.config["instance"],
                    "--tag",
                    "developer-platform",
                ]
            )
        )
        dirty = []
        for item in snapshots:
            snapshot_id = item["id"]
            manifest = json.loads(
                job.command([job.restic, "dump", snapshot_id, "bundle/manifest.json"])
            )
            if identity in manifest.get("project_ids", []):
                dirty.append(snapshot_id)
            elif "project_ids" not in manifest:
                raise MaintenanceError("Backup lacks a project ownership manifest")
        if clean in dirty or any(
            clean.startswith(item) or item.startswith(clean) for item in dirty
        ):
            raise MaintenanceError("The new backup still contains the project")
        if dirty:
            job.command([job.restic, "forget", "--prune", *dirty])
        # The restore verifier checks UUID ownership again; a snapshot invisible
        # in the index is not sufficient proof until repository pruning passes.
        job.command([job.restic, "check"])
        for directory in (job.state / "work", root / ".runtime/backups"):
            if directory.exists():
                if directory.is_symlink():
                    raise MaintenanceError("Unsafe recovery directory")
                shutil.rmtree(directory)


def run(root, backup_config):
    requests = root / ".runtime/maintenance"
    if not requests.is_dir():
        return
    for path in sorted(requests.glob("*.request.json")):
        operation_id = str(UUID(path.name.removesuffix(".request.json")))
        if (requests / (operation_id + ".final.json")).exists():
            continue
        operation = json.loads(api(root, "inspect", operation_id))
        if operation["step"] == "external_erasure":
            # Stop the collector before removing node logs and tenant stores.
            # Its in-memory batches must not recreate a just-erased stream.
            command(["docker", "compose", "stop", "alloy"], root)
            try:
                remove_workload_logs(root, operation["project"])
                remove_tenant(root, operation["project_id"])
                loki_root = (
                    command(
                        [
                            "docker",
                            "volume",
                            "inspect",
                            "developer-platform_loki",
                            "--format",
                            "{{.Mountpoint}}",
                        ],
                        root,
                    )
                    .decode()
                    .strip()
                )
                if not loki_root.startswith("/var/lib/docker/volumes/"):
                    raise MaintenanceError("Unexpected Loki volume location")
                remove_tenant(
                    root, operation["project_id"], Path(loki_root), service="loki"
                )
                api(root, "operational", operation_id)
                if api(root, "verify-traces", operation_id, allow_pending=True) is None:
                    continue
                if api(root, "verify-logs", operation_id, allow_pending=True) is None:
                    continue
                api(root, "receipt", operation_id)
            finally:
                command(["docker", "compose", "start", "alloy"], root)
        elif operation["step"] == "catalog_removed":
            clean_backups(root, operation["project_id"], backup_config)
            api(root, "final", operation_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform-dir", type=Path, default=Path("/opt/developer-platform")
    )
    parser.add_argument(
        "--backup-config",
        type=Path,
        default=Path("/etc/developer-platform/backup/job.json"),
    )
    args = parser.parse_args()
    run(args.platform_dir, args.backup_config)


if __name__ == "__main__":
    main()
