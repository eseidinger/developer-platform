#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.runtime/bin:$PATH"
for tool in docker k3d kubectl python3; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done
test -f .env || { echo "Run python3 scripts/init.py first" >&2; exit 1; }
# Only generated KEY=value settings are accepted; never source arbitrary shell code.
eval "$(python3 scripts/env.py)"
umask 077
mkdir -p .runtime
echo "Starting PostgreSQL and waiting for it to become healthy..."
docker compose up -d --wait --wait-timeout 120 postgres
python3 scripts/cluster_config.py > .runtime/k3d.yaml
if ! k3d cluster list -o json | python3 -c 'import json,sys; sys.exit(not any(c["name"] == "workloads" for c in json.load(sys.stdin)))'; then
  k3d cluster create --config .runtime/k3d.yaml
else
  k3d cluster start workloads
fi
k3d kubeconfig get workloads > .runtime/admin.kubeconfig
export KUBECONFIG="$PWD/.runtime/admin.kubeconfig"
echo "Waiting for Kubernetes nodes to become Ready (up to 180 seconds)..."
kubectl wait --for=condition=Ready nodes --all --timeout=180s
kubectl apply -f infrastructure/kubernetes/controller.yaml
kubectl apply -f infrastructure/kubernetes/metrics.yaml
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret provisioner-token -o json > .runtime/token.json
  if python3 scripts/kubeconfig.py; then break; fi
  sleep 2
done
test -s .runtime/controller.kubeconfig
# Container UID 10001 needs read access; .runtime remains private to the host user.
chmod 644 .runtime/controller.kubeconfig
rm -f .runtime/token.json
docker compose up -d --build
echo "Platform API: http://127.0.0.1:8000/docs"
