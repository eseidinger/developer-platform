import base64
import json
from pathlib import Path
secret = json.loads(Path(".runtime/token.json").read_text())
data = secret.get("data", {})
if not data.get("token"):
    raise SystemExit(1)
config = {
    "apiVersion": "v1", "kind": "Config",
    "clusters": [{"name": "workloads", "cluster": {
        "server": "https://k3d-workloads-server-0:6443",
        "certificate-authority-data": data["ca.crt"]}}],
    "users": [{"name": "provisioner", "user": {
        "token": base64.b64decode(data["token"]).decode()}}],
    "contexts": [{"name": "workloads", "context": {
        "cluster": "workloads", "user": "provisioner"}}],
    "current-context": "workloads"}
Path(".runtime/controller.kubeconfig").write_text(json.dumps(config))
