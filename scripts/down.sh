#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.runtime/bin:$PATH"

volumes=()
case "${1:-}" in
  --volumes) volumes=(--volumes) ;;
  -h|--help)
    echo "Usage: bash scripts/down.sh [--volumes]"
    echo "Remove the workloads cluster and Compose services; --volumes also deletes persistent service data."
    echo "Preserves .env, backups, and installed tools."
    exit 0 ;;
  "") ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  echo "Usage: bash scripts/down.sh [--volumes]" >&2
  exit 2
fi

for tool in docker k3d python3; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done
test -f .env || { echo "Missing .env; restore the platform configuration before teardown." >&2; exit 1; }
eval "$(python3 scripts/env.py)"
# Validate configuration before removing any resources.
docker compose config --quiet
clusters=$(k3d cluster list -o json)
cluster_exists=$(python3 -c 'import json,sys; print(any(c["name"] == "workloads" for c in json.load(sys.stdin)))' <<< "$clusters")
if [[ "$cluster_exists" == True ]]; then
  echo "Deleting Kubernetes cluster workloads..."
  # Keep k3d from modifying the user's default kubeconfig.
  KUBECONFIG="$PWD/.runtime/admin.kubeconfig" k3d cluster delete workloads
fi
# Delete the cluster first so its nodes no longer hold the Compose network open.
echo "Removing Compose services and network..."
docker compose down "${volumes[@]}"
python3 - <<'PY'
from pathlib import Path
for name in ("admin.kubeconfig", "controller.kubeconfig", "token.json", "k3d.yaml"):
    (Path(".runtime") / name).unlink(missing_ok=True)
PY
if (( ${#volumes[@]} )); then
  echo "Platform removed, including persistent service data. .env and backups were preserved."
else
  echo "Platform removed. Persistent service data, .env, and backups were preserved."
  echo "After bootstrap, reapply saved project specs to recreate Kubernetes workloads."
fi
