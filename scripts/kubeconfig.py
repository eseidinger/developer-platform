import base64
import json
import argparse
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--log-reader", action="store_true")
args = parser.parse_args()
account = "workload-log-reader" if args.log_reader else "provisioner"
token_file = ".runtime/log-reader-token.json" if args.log_reader else ".runtime/token.json"
output_file = ".runtime/log-reader.kubeconfig" if args.log_reader else ".runtime/controller.kubeconfig"
secret = json.loads(Path(token_file).read_text())
data = secret.get("data", {})
if not data.get("token"):
    raise SystemExit(1)
config = {
    "apiVersion": "v1", "kind": "Config",
    "clusters": [{"name": "workloads", "cluster": {
        "server": "https://k3d-workloads-server-0:6443",
        "certificate-authority-data": data["ca.crt"]}}],
    "users": [{"name": account, "user": {
        "token": base64.b64decode(data["token"]).decode()}}],
    "contexts": [{"name": "workloads", "context": {
        "cluster": "workloads", "user": account}}],
    "current-context": "workloads"}
Path(output_file).write_text(json.dumps(config))
