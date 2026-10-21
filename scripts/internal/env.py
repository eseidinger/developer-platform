import os
import re
import shlex
from pathlib import Path


def parse_environment(source):
    """Read literal KEY=value settings without evaluating shell expressions."""
    result = {}
    for line in source.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("Invalid setting")
        result[key] = value
    return result


def settings():
    return {
        key: os.environ.get(key, value)
        for key, value in parse_environment(Path(".env").read_text()).items()
    }


if __name__ == "__main__":
    for key, value in settings().items():
        print("export " + key + "=" + shlex.quote(value))
