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
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID


class MaintenanceError(Exception):
    pass


def command(args, root, allow_pending=False, data=None):
    result = subprocess.run(
        args,
        cwd=root,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
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
        if service == "tempo":
            # Tempo's shared scheduler files can still hold pending per-tenant
            # jobs after their blocks have been erased. Preserve other jobs.
            for shard in storage.glob("shard_*.json"):
                state = json.loads(shard.read_text())
                jobs = state["jobs"]
                if not isinstance(jobs, dict):
                    raise MaintenanceError("Unexpected trace scheduler format")
                retained = {
                    key: value
                    for key, value in jobs.items()
                    if tenant not in json.dumps({key: value})
                }
                if retained != jobs:
                    state["jobs"] = retained
                    temporary = shard.with_suffix(".tmp")
                    temporary.write_text(json.dumps(state))
                    permissions = shard.stat()
                    os.chmod(temporary, permissions.st_mode & 0o777)
                    os.chown(temporary, permissions.st_uid, permissions.st_gid)
                    temporary.replace(shard)
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


def volume_root(root, service, destination):
    container = (
        command(["docker", "compose", "ps", "-q", service], root).decode().strip()
    )
    mounts = json.loads(
        command(["docker", "inspect", container, "--format", "{{json .Mounts}}"], root)
    )
    candidates = [
        Path(item["Source"])
        for item in mounts
        if item["Destination"] == destination and item["Type"] == "volume"
    ]
    if len(candidates) != 1 or not str(candidates[0]).startswith(
        "/var/lib/docker/volumes/"
    ):
        raise MaintenanceError("Unexpected telemetry volume location")
    return candidates[0]


def rebuild_logs(root, operation):
    identity = str(UUID(operation["operation_id"]))
    api(root, "export-logs", identity)
    storage = volume_root(root, "loki", "/loki")
    backup = root / ".runtime/maintenance" / (identity + ".loki-old")
    marker = backup.with_suffix(".rebuilding")
    command(["docker", "compose", "stop", "loki"], root)
    try:
        backup.mkdir(mode=0o700, exist_ok=True)
        for path in storage.iterdir():
            if path.is_symlink():
                raise MaintenanceError("Unexpected symlink in log storage")
            if marker.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            else:
                path.rename(backup / path.name)
        marker.touch(mode=0o600)
    finally:
        command(["docker", "compose", "start", "loki"], root)
    # If replay fails, the private export and original volume survive. The next
    # systemd run resumes from the same export and verifies each retained stream.
    api(root, "restore-logs", identity)
    if api(root, "verify-logs", identity, allow_pending=True) is None:
        raise MaintenanceError("Project logs remain after rebuild")
    shutil.rmtree(backup)
    marker.unlink()
    (root / ".runtime/maintenance" / (identity + ".loki-clean.jsonl")).unlink()


def compact_metrics(root, operation):
    staging = (
        root
        / ".runtime/maintenance"
        / (str(UUID(operation["operation_id"])) + ".metrics-clean")
    )
    # Resume the durable clean copy before asking a partially rebuilt server for
    # another snapshot. It may have been stopped when the host process exited.
    snapshot = (
        "20260101T000000Z-0"
        if staging.exists()
        else json.loads(api(root, "operational", operation["operation_id"]))["snapshot"]
    )
    rebuild_metrics(root, snapshot, operation["operation_id"])


def rebuild_metrics(root, snapshot, operation_id):
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]+", snapshot):
        raise MaintenanceError("Unexpected metric snapshot name")
    storage = volume_root(root, "prometheus", "/prometheus")
    staging = (
        root / ".runtime/maintenance" / (str(UUID(operation_id)) + ".metrics-clean")
    )
    if staging.is_symlink():
        raise MaintenanceError("Unsafe metric staging directory")
    if not staging.exists():
        source = storage / "snapshots" / snapshot
        if source.is_symlink() or not source.is_dir():
            raise MaintenanceError("Clean metric snapshot is missing")
        temporary = staging.with_suffix(".tmp")
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(source, temporary)
        temporary.rename(staging)
    command(["docker", "compose", "stop", "prometheus"], root)
    try:
        for path in storage.iterdir():
            if path.is_symlink():
                raise MaintenanceError("Unexpected symlink in metric storage")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for path in staging.iterdir():
            if path.is_dir():
                shutil.copytree(path, storage / path.name)
            else:
                shutil.copy2(path, storage / path.name)
        owner = storage.stat()
        for path in storage.rglob("*"):
            os.chown(path, owner.st_uid, owner.st_gid)
    finally:
        command(["docker", "compose", "start", "prometheus"], root)
    shutil.rmtree(staging)


def remove_reports(root, operation):
    """Remove combined test evidence that identifies the purged project."""
    project, identity = operation["project"], operation["project_id"]

    def associated(value):
        if isinstance(value, dict):
            return any(
                (
                    key
                    in {"project", "project_id", "providerProject", "consumer_project"}
                    and item in (project, identity)
                )
                or associated(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(associated(item) for item in value)
        return value in (project, identity)

    for name in (
        "application-lifecycle",
        "hosted-access",
        "human-database-access",
        "data-preservation",
        "interrupted-provisioning",
        "isolation",
    ):
        reports = root / ".runtime" / name
        if reports.is_symlink():
            raise MaintenanceError("Unsafe report directory")
        if not reports.exists():
            continue
        for run_directory in reports.iterdir():
            if run_directory.is_symlink() or not run_directory.is_dir():
                raise MaintenanceError("Unexpected operational report layout")
            for path in run_directory.glob("*.json"):
                if path.is_symlink():
                    raise MaintenanceError("Unsafe report file")
                if associated(json.loads(path.read_text())):
                    shutil.rmtree(run_directory)
                    break


def clean_backups(root, identity, backup_config, operation_id):
    if not backup_config.exists():
        # Backups are optional on a fresh local installation. An old state or
        # installed job without configuration is ambiguous and must block.
        if (
            Path("/var/lib/developer-platform-backup").exists()
            or Path("/etc/systemd/system/platform-backup.service").exists()
        ):
            raise MaintenanceError("Existing backup installation lacks configuration")
        local = root / ".runtime/backups"
        if local.is_symlink():
            raise MaintenanceError("Unsafe local backup directory")
        if local.exists():
            shutil.rmtree(local)
        return
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
        previous_run = job.read("status.json", {}).get("run_id")
        job.run()
        status = job.read("status.json", {})
        if (
            status.get("running")
            or status.get("result") != "success"
            or status.get("run_id") == previous_run
            or status.get("last_verified_capture") != status.get("started")
            or not status.get("last_verified_snapshot")
        ):
            raise MaintenanceError("No verified clean backup")
        clean = status["last_verified_snapshot"]
        snapshots = json.loads(
            job.command(
                [
                    job.restic,
                    "snapshots",
                    "--json",
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
                # Unknown historical ownership is included in the explicitly
                # confirmed backup-erasure scope, never certified as clean.
                dirty.append(snapshot_id)
        if clean in dirty or any(
            clean.startswith(item) or item.startswith(clean) for item in dirty
        ):
            raise MaintenanceError("The new backup still contains the project")
        if dirty:
            job.command([job.restic, "forget", "--prune", *dirty])
        # The restore verifier checks UUID ownership again; a snapshot invisible
        # in the index is not sufficient proof until repository pruning passes.
        # The protected shell file contains only literal KEY=quoted-value lines.
        # Parse it without executing shell code or exposing credentials in argv.
        configuration = {}
        for line in (
            Path("/etc/developer-platform/backup/restic.env").read_text().splitlines()
        ):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            values = shlex.split(line)
            if len(values) != 1 or "=" not in values[0]:
                raise MaintenanceError("Unexpected backup environment format")
            key, value = values[0].split("=", 1)
            if key in {
                "RESTIC_REPOSITORY",
                "AWS_DEFAULT_REGION",
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
            }:
                configuration[key] = value
        command(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "platform-api",
                "python",
                "-m",
                "app.lifecycle.backup_versions",
            ],
            root,
            data=json.dumps(
                {"operation_id": operation_id, "configuration": configuration}
            ).encode(),
        )
        job.command([job.restic, "check"])
        repository_id = json.loads(job.command([job.restic, "cat", "config"]))["id"]
        if not re.fullmatch(r"[0-9a-f]{64}", repository_id):
            raise MaintenanceError("Unexpected backup repository identity")
        cache = Path("/root/.cache/restic") / repository_id
        if cache.is_symlink():
            raise MaintenanceError("Unsafe backup cache")
        if cache.exists():
            shutil.rmtree(cache)
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
            command(["docker", "compose", "stop", "alloy", "trace-router"], root)
            try:
                remove_workload_logs(root, operation["project"])
                remove_reports(root, operation)
                remove_tenant(root, operation["project_id"])
                rebuild_logs(root, operation)
                compact_metrics(root, operation)
                if api(root, "verify-traces", operation_id, allow_pending=True) is None:
                    continue
                if api(root, "verify-logs", operation_id, allow_pending=True) is None:
                    continue
                api(root, "receipt", operation_id)
            finally:
                # Do not ingest new records into a half rebuilt log store. The
                # next timer run uses the complete retained export to resume.
                command(["docker", "compose", "start", "trace-router"], root)
                if not (requests / (operation_id + ".loki-clean.jsonl")).exists():
                    command(["docker", "compose", "start", "alloy"], root)
        elif operation["step"] == "catalog_removed":
            remove_reports(root, operation)
            # Catalog exporters may have emitted one last store series while
            # deletion was waiting. Compact again after every owned row is gone.
            compact_metrics(root, operation)
            clean_backups(root, operation["project_id"], backup_config, operation_id)
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
    handoff = args.platform_dir / ".runtime/maintenance"
    if not handoff.is_dir():
        return
    with (handoff / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        run(args.platform_dir, args.backup_config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - Never send private paths/provider payloads to the shared journal.
        print(
            "Project purge maintenance incomplete: " + type(exc).__name__,
            file=sys.stderr,
        )
        raise SystemExit(1) from None
