import os
import re
import shlex
from pathlib import Path

def settings():
    result = {}
    for line in Path(".env").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("Invalid setting")
        result[key] = os.environ.get(key, value)
    return result

if __name__ == "__main__":
    for key, value in settings().items():
        print("export " + key + "=" + shlex.quote(value))
