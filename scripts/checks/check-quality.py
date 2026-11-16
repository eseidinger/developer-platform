#!/usr/bin/env python3
"""Lint tracked source, or every added/modified file relative to a CI base commit.

Historical documents remain immutable. Deleted files and untracked local
inventories/secrets are never passed to tools. A full scan is available to audit
older source separately from the changes a pull request introduces.
"""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def files(base=None):
    arguments = ["git", "ls-files", "-z"]
    if base:
        arguments = [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
            base,
            "HEAD",
        ]
    names = subprocess.check_output(arguments, cwd=ROOT).decode().split("\0")
    return [
        name
        for name in names
        if name and (ROOT / name).is_file() and not name.startswith("docs/history/")
    ]


def commands(paths):
    python = [p for p in paths if p.endswith(".py")]
    yaml = [p for p in paths if p.endswith((".yaml", ".yml"))]
    markdown = [p for p in paths if p.endswith(".md")]
    shell = [p for p in paths if p.endswith(".sh")]
    docker = [p for p in paths if Path(p).name == "Dockerfile"]
    ansible = [p for p in yaml if p.startswith("ansible/") or "/ansible/" in p]
    for command, selected in (
        (["ruff", "check"], python),
        (["ruff", "format", "--check"], python),
        (["yamllint"], yaml),
        (["ansible-lint"], ansible),
        (["pymarkdown", "scan"], markdown),
        (["mdformat", "--check"], markdown),
        (["shellcheck"], shell),
        (["hadolint"], docker),
    ):
        if selected:
            yield command + selected
    for path in shell:
        yield ["bash", "-n", path]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", help="Lint all changes since this commit; omit for a full audit"
    )
    args = parser.parse_args()
    failed = False
    for command in commands(files(args.base)):
        print(f"+ {command[0]} ({len(command) - 1} arguments)", flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        failed |= result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
