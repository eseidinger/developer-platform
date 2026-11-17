#!/usr/bin/env python3
"""Reconcile operator Loki and Tempo data sources with catalog project IDs."""

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "infrastructure/monitoring/datasources.yaml"
TARGET = ROOT / ".runtime/grafana-datasources/default.yaml"
PROJECT_NAME = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")


def project_sources(projects):
    """Render stable, project-scoped sources; UUIDs change after complete purge."""
    entries = []
    for name, identifier in sorted(projects):
        if not PROJECT_NAME.fullmatch(name):
            raise ValueError("Invalid catalog project name")
        project_id = str(UUID(identifier))
        if project_id != identifier:
            raise ValueError("Project ID must be a canonical UUID")
        for source, url in (
            ("Loki", "http://loki:3100"),
            ("Tempo", "http://tempo:3200"),
        ):
            entries.extend(
                (
                    f"  - name: {json.dumps(f'{source} project {name}')}\n",
                    f"    type: {source.lower()}\n",
                    f"    uid: {source.lower()}-{UUID(identifier).hex}\n",
                    f"    url: {url}\n",
                    "    access: proxy\n",
                    "    jsonData:\n",
                    "      httpHeaderName1: X-Scope-OrgID\n",
                    "    secureJsonData:\n",
                    f"      httpHeaderValue1: {project_id}\n",
                )
            )
    return "".join(entries)


def render(base, projects):
    """Keep shared sources from the repository and append derived project sources."""
    if not base.endswith("\n") or "prune: true\n" not in base:
        raise ValueError("Base Grafana provisioning must enable pruning")
    return base + project_sources(projects)


def replace_if_changed(path, content):
    """Replace the directory entry atomically so Grafana reads a complete file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    # The caller may use umask 077; Grafana UID 472 still needs to list the
    # bind-mounted directory. Only project names and UUIDs appear here.
    path.parent.chmod(0o755)
    if path.exists() and path.read_text() == content:
        return False
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o644)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def docker(*arguments):
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def catalog_projects():
    """Use the API container's restricted telemetry role, not host DB secrets."""
    rows = json.loads(
        docker("exec", "-T", "platform-api", "python", "-m", "app.telemetry_catalog")
    )
    if not isinstance(rows, list):
        raise ValueError("Invalid project catalog response")
    return rows


def grafana_running():
    services = docker("ps", "--status", "running", "--services", "grafana")
    return "grafana" in services.splitlines()


def wait_for_grafana():
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:3000/api/health", timeout=2):
                return
        except (OSError, TimeoutError):
            time.sleep(1)
    raise RuntimeError("Grafana did not become ready after restart")


def reconcile(*, restart=True):
    content = render(BASE.read_text(), catalog_projects())
    changed = replace_if_changed(TARGET, content)
    if changed and restart and grafana_running():
        # A changed provisioning file needs a reload. Restart avoids depending
        # on the bootstrap admin password, which an operator may have rotated.
        docker("restart", "grafana")
        wait_for_grafana()
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Generate sources before the normal Compose startup",
    )
    arguments = parser.parse_args()
    changed = reconcile(restart=not arguments.no_restart)
    message = (
        "Grafana project data sources updated."
        if changed
        else "Grafana project data sources current."
    )
    print(message)


if __name__ == "__main__":
    main()
