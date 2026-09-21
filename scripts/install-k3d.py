#!/usr/bin/env python3
"""Install a checksum-verified k3d release inside this project, not system-wide."""
import hashlib
import platform
import urllib.request
from pathlib import Path
version = "v5.8.3"
arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
asset = "k3d-linux-" + arch
url = "https://github.com/k3d-io/k3d/releases/download/" + version + "/"
data = urllib.request.urlopen(url + asset, timeout=60).read()
checksums = urllib.request.urlopen(url + "checksums.txt", timeout=30).read().decode()
expected = next(line.split()[0] for line in checksums.splitlines() if Path(line.split()[-1].lstrip("*")).name == asset)
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit("Checksum mismatch")
target = Path(__file__).resolve().parents[1] / ".runtime/bin/k3d"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(data)
target.chmod(0o755)
print("Installed", version, "in", target)
