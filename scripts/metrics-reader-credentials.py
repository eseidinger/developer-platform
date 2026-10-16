"""Extract only the Prometheus Kubernetes proxy credential from a token secret."""
import base64
import json
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capacity", action="store_true")
prefix = "capacity-reader" if parser.parse_args().capacity else "metrics-reader"
data = json.loads(Path(f".runtime/{prefix}-token.json").read_text())["data"]
for field, output in (("token", f"{prefix}.token"), ("ca.crt", f"{prefix}-ca.crt")):
    value = base64.b64decode(data[field])
    if not value:
        raise SystemExit("Empty metrics reader credential")
    Path(".runtime", output).write_bytes(value)
