#!/usr/bin/env python3
"""Reject CLI tags that do not name the exact version in the distribution."""

import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = re.compile(r"cli-v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))")


def validate(reference_type, tag, package_version):
    match = TAG.fullmatch(tag)
    if reference_type != "tag" or match is None:
        raise ValueError("CLI releases require a cli-vMAJOR.MINOR.PATCH tag")
    if match[1] != package_version:
        raise ValueError(
            f"Release tag {tag} does not match package version {package_version}"
        )
    return package_version


def main():
    version = tomllib.loads((ROOT / "platform/cli/pyproject.toml").read_text())[
        "project"
    ]["version"]
    validate(
        os.environ.get("GITHUB_REF_TYPE"),
        os.environ.get("GITHUB_REF_NAME", ""),
        version,
    )
    print(f"Validated CLI release {version}")


if __name__ == "__main__":
    main()
