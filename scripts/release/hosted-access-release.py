#!/usr/bin/env python3
"""Validated, non-secret metadata for a hosted-access fixture tag release."""
import os
from pathlib import Path
import re
import sys


TAG = re.compile(r"hosted-access-v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))")
NAMESPACE = re.compile(r"[a-z0-9][a-z0-9_-]*")


def metadata(environment):
    match = TAG.fullmatch(environment.get("GITHUB_REF_NAME", ""))
    if environment.get("GITHUB_REF_TYPE") != "tag" or match is None:
        raise ValueError("Publish only a hosted-access-vMAJOR.MINOR.PATCH Git tag (for example hosted-access-v0.1.0).")
    username = environment.get("DOCKERHUB_USERNAME", "")
    namespace = environment.get("DOCKERHUB_NAMESPACE") or username
    if not NAMESPACE.fullmatch(username) or not NAMESPACE.fullmatch(namespace):
        raise ValueError("Set DOCKERHUB_USERNAME and, optionally, DOCKERHUB_NAMESPACE to valid lowercase Docker Hub names.")
    return {"version": match[1], "image": "docker.io/" + namespace + "/developer-platform-acceptance-fixture"}


def main():
    try:
        release = metadata(os.environ)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key, value in release.items():
            print(f"{key}={value}", file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
