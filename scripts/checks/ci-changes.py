#!/usr/bin/env python3
"""Detect code changes before starting disposable component jobs."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def selection(event_name, event):
    if event_name == "pull_request":
        base = subprocess.check_output(
            ["git", "merge-base", event["pull_request"]["base"]["sha"], "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    elif (
        event_name == "push"
        and event.get("before", "").strip("0")
        and not event.get("ref", "").startswith("refs/tags/")
    ):
        base = event["before"]
    else:
        # Releases, scheduled audits and manual runs always execute all jobs.
        return {"base": "", "components": "true"}
    paths = (
        subprocess.check_output(
            ["git", "diff", "--name-only", "-z", base, "HEAD"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    # Machine-readable contracts under docs/ are application inputs. Only
    # Markdown prose may bypass the runtime and generated-contract checks.
    components = any(p and not p.endswith(".md") for p in paths)
    return {"base": base, "components": str(components).lower()}


def main():
    result = selection(
        os.environ["GITHUB_EVENT_NAME"],
        json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for key, value in result.items():
            print(f"{key}={value}", file=output)


if __name__ == "__main__":
    main()
