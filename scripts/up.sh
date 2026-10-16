#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.runtime/bin:$PATH"
for tool in docker k3d kubectl python3 setfacl; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done
test -f .env || { echo "Run python3 scripts/init.py first" >&2; exit 1; }
if ! mountpoint -q /var/lib/developer-platform/tempo; then
  echo "Prepare the bounded trace filesystem: sudo bash scripts/prepare-tempo-storage.sh" >&2
  exit 1
fi
python3 scripts/check-network-addresses.py
# Only generated KEY=value settings are accepted; never source arbitrary shell code.
eval "$(python3 scripts/env.py)"
umask 077
mkdir -p .runtime
chmod 700 .runtime
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
if ! kubectl --request-timeout=5s get --raw=/readyz >/dev/null 2>&1; then
  # The k3d load balancer resolves its named upstream when nginx starts. After
  # a Docker daemon restart the node can receive a different address while the
  # load balancer retains the old resolution. Restarting only the load balancer
  # refreshes that resolution without recreating the cluster or its data.
  echo "Refreshing the k3d API load balancer..."
  docker restart k3d-workloads-serverlb >/dev/null
fi
echo "Waiting for the Kubernetes API to become ready (up to 120 seconds)..."
for attempt in $(seq 1 24); do
  if kubectl --request-timeout=5s get --raw=/readyz >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == 24 ]]; then
    echo "Kubernetes API did not become ready." >&2
    exit 1
  fi
  sleep 5
done
echo "Waiting for Kubernetes nodes to become Ready (up to 180 seconds)..."
kubectl wait --for=condition=Ready nodes --all --timeout=180s
kubectl apply -f infrastructure/kubernetes/controller.yaml
kubectl apply -f infrastructure/kubernetes/metrics.yaml
kubectl apply -f infrastructure/kubernetes/log-reader.yaml
kubectl apply -f infrastructure/kubernetes/metrics-reader.yaml
kubectl apply -f infrastructure/kubernetes/telemetry-reviewer.yaml
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret provisioner-token -o json > .runtime/token.json
  if python3 scripts/kubeconfig.py; then break; fi
  sleep 2
done
test -s .runtime/controller.kubeconfig
# Give only the Platform API's UID read access to its scoped credential.
setfacl -b .runtime/controller.kubeconfig
chmod 600 .runtime/controller.kubeconfig
setfacl -m u:10001:r-- .runtime/controller.kubeconfig
rm -f .runtime/token.json
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret workload-log-reader-token -o json > .runtime/log-reader-token.json
  if python3 scripts/kubeconfig.py --log-reader; then break; fi
  sleep 2
done
test -s .runtime/log-reader.kubeconfig
# Alloy runs as UID 0 with all capabilities dropped. Its bind mount exposes
# only this log-reader credential, even when bootstrap runs as a non-root user.
setfacl -b .runtime/log-reader.kubeconfig
chmod 600 .runtime/log-reader.kubeconfig
setfacl -m u:0:r-- .runtime/log-reader.kubeconfig
rm -f .runtime/log-reader-token.json
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret workload-metrics-reader-token -o json > .runtime/metrics-reader-token.json
  if python3 scripts/metrics-reader-credentials.py; then break; fi
  sleep 2
done
test -s .runtime/metrics-reader.token
test -s .runtime/metrics-reader-ca.crt
setfacl -b .runtime/metrics-reader.token
chmod 600 .runtime/metrics-reader.token
setfacl -m u:65534:r-- .runtime/metrics-reader.token
chmod 644 .runtime/metrics-reader-ca.crt
rm -f .runtime/metrics-reader-token.json
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret telemetry-reviewer-token -o json > .runtime/telemetry-reviewer-token.json
  if python3 scripts/kubeconfig.py --telemetry-reviewer; then break; fi
  sleep 2
done
test -s .runtime/telemetry-reviewer.kubeconfig
setfacl -b .runtime/telemetry-reviewer.kubeconfig
chmod 600 .runtime/telemetry-reviewer.kubeconfig
setfacl -m u:10001:r-- .runtime/telemetry-reviewer.kubeconfig
rm -f .runtime/telemetry-reviewer-token.json
docker build -f platform/Dockerfile.telemetry-forwarder -t developer-platform-telemetry-forwarder:local platform
k3d image import developer-platform-telemetry-forwarder:local -c workloads
# Claim the fixed identity/API addresses before monitoring and edge containers
# can receive them from Docker's dynamic allocator. This starts only the API's
# required dependencies (PostgreSQL and the two identity initializers).
python3 scripts/check-network-addresses.py
echo "Starting fixed-address identity and Platform API services first..."
docker compose up -d --build --wait --wait-timeout 180 platform-api
python3 scripts/check-network-addresses.py
docker compose up -d --build --remove-orphans
echo "Waiting for the Alloy collector to become ready (up to 120 seconds)..."
docker compose up -d --no-deps --wait --wait-timeout 120 alloy
docker build -f platform/Dockerfile.access -t developer-platform-access-authorizer:local platform
k3d image import developer-platform-access-authorizer:local -c workloads
python3 scripts/install-application-access.py
echo "Platform API: http://127.0.0.1:8000/docs"
