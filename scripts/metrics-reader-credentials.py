"""Extract only the Prometheus Kubernetes proxy credential from a token secret."""
import base64
import json
from pathlib import Path

data = json.loads(Path(".runtime/metrics-reader-token.json").read_text())["data"]
for field, output in (("token", "metrics-reader.token"), ("ca.crt", "metrics-reader-ca.crt")):
    value = base64.b64decode(data[field])
    if not value:
        raise SystemExit("Empty metrics reader credential")
    Path(".runtime", output).write_bytes(value)
