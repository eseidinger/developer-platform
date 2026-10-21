#!/usr/bin/env bash
set -euo pipefail

# --- Prerequisites and local configuration ---

# Resolve all repository paths from the checkout and prefer locally installed tools.
cd "$(dirname "$0")/.."
export PATH="$PWD/.runtime/bin:$PATH"

for tool in docker k3d kubectl python3 setfacl findmnt; do
  command -v "$tool" >/dev/null || {
    echo "Missing prerequisite: $tool" >&2
    exit 1
  }
done

test -f .env || {
  echo "Run python3 scripts/init.py first" >&2
  exit 1
}

# Validate shared settings and synchronize tracing before starting services.
python3 scripts/setup/configure-platform.py --runtime

# Prepare store keys and configuration, then check the trace storage mount.
python3 scripts/setup/prepare-stores.py

# Inspect the mount table: the private parent directory is intentionally root-only.
if ! findmnt --mountpoint /var/lib/developer-platform/tempo --noheadings >/dev/null; then
  echo "Prepare the bounded trace filesystem: sudo bash scripts/setup/prepare-tempo-storage.sh" >&2
  exit 1
fi

python3 scripts/checks/check-network-addresses.py

# Only generated KEY=value settings are accepted; never source arbitrary shell code.
eval "$(python3 scripts/internal/env.py)"

# Keep generated credentials private from the moment they are written.
umask 077
mkdir -p .runtime
chmod 700 .runtime

python3 scripts/generate/generate-dashboards.py

# --- PostgreSQL and selected persistent stores ---

# PostgreSQL must be healthy before reconciling its monitoring login.
echo "Starting PostgreSQL and waiting for it to become healthy..."
docker compose up -d --wait --wait-timeout 120 postgres
python3 scripts/setup/setup-postgres-monitoring.py

# Claim selected stores' fixed addresses before dynamically addressed services.
# The initializer is a one-shot job; wait for persistent services separately.
store_services=()
IFS=',' read -ra store_profiles <<< "${COMPOSE_PROFILES:-}"
for profile in "${store_profiles[@]}"; do
  case "$profile" in
    s3)
      store_services+=(rustfs)
      ;;
    qdrant)
      store_services+=(qdrant)
      ;;
    neo4j)
      docker build -t developer-platform-neo4j:2026.09.0-community-jmx1.6.0 \
        infrastructure/persistence/neo4j
      store_services+=(neo4j-controller)
      ;;
    opensearch)
      store_services+=(opensearch)
      docker compose up -d opensearch-init
      ;;
  esac
done

if (( ${#store_services[@]} )); then
  echo "Starting selected persistent data stores..."
  docker compose up -d --wait --wait-timeout 240 "${store_services[@]}"
fi

# OpenSearch initialization must finish before its console is started.
if [[ ",${COMPOSE_PROFILES:-}," == *,opensearch,* ]]; then
  initializer=$(docker compose ps -aq opensearch-init)
  for attempt in $(seq 1 60); do
    state=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$initializer")
    if [[ "$state" == 'exited 0' ]]; then
      break
    fi
    if [[ "$state" == exited* || "$attempt" == 60 ]]; then
      echo "OpenSearch initialization failed or timed out; inspect private initializer diagnostics." >&2
      exit 1
    fi
    sleep 2
  done

  # Reserve the console's isolated address before any dynamically addressed peer.
  # Its native backend becomes available when the API starts later in bootstrap.
  docker compose up -d --no-deps opensearch-dashboards
fi

# --- Workload cluster and Kubernetes readiness ---

# Reuse the existing cluster when available; otherwise create it from local settings.
python3 scripts/internal/cluster_config.py > .runtime/k3d.yaml
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

# Discover the node network used by Kubernetes service proxies.
kubectl get nodes -o json | python3 scripts/internal/metrics-proxy-network.py

# Refresh generated operator settings before Compose creates the API container.
unset PLATFORM_METRICS_PROXY_CIDRS
eval "$(python3 scripts/internal/env.py)"

# --- Scoped Kubernetes credentials ---

# Create the service accounts and permissions before waiting for their tokens.
kubectl apply -f infrastructure/kubernetes/controller.yaml
kubectl apply -f infrastructure/kubernetes/metrics.yaml
kubectl apply -f infrastructure/kubernetes/log-reader.yaml
kubectl apply -f infrastructure/kubernetes/metrics-reader.yaml
kubectl apply -f infrastructure/kubernetes/capacity-reader.yaml
kubectl apply -f infrastructure/kubernetes/telemetry-reviewer.yaml

# Platform API: provisioner kubeconfig. Token secrets can take time to populate.
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret provisioner-token -o json > .runtime/token.json
  if python3 scripts/internal/kubeconfig.py; then
    break
  fi
  sleep 2
done

test -s .runtime/controller.kubeconfig
# Give only the Platform API's UID read access to its scoped credential.
setfacl -b .runtime/controller.kubeconfig
chmod 600 .runtime/controller.kubeconfig
setfacl -m u:10001:r-- .runtime/controller.kubeconfig
rm -f .runtime/token.json

# Alloy: read-only access to workload logs.
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret workload-log-reader-token -o json > .runtime/log-reader-token.json
  if python3 scripts/internal/kubeconfig.py --log-reader; then
    break
  fi
  sleep 2
done

test -s .runtime/log-reader.kubeconfig
# Alloy runs as UID 0 with all capabilities dropped. Its bind mount exposes
# only this log-reader credential, even when bootstrap runs as a non-root user.
setfacl -b .runtime/log-reader.kubeconfig
chmod 600 .runtime/log-reader.kubeconfig
setfacl -m u:0:r-- .runtime/log-reader.kubeconfig
rm -f .runtime/log-reader-token.json

# Prometheus: workload metrics token and public CA certificate.
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret workload-metrics-reader-token -o json > .runtime/metrics-reader-token.json
  if python3 scripts/internal/metrics-reader-credentials.py; then
    break
  fi
  sleep 2
done

test -s .runtime/metrics-reader.token
test -s .runtime/metrics-reader-ca.crt
setfacl -b .runtime/metrics-reader.token
chmod 600 .runtime/metrics-reader.token
setfacl -m u:65534:r-- .runtime/metrics-reader.token
chmod 644 .runtime/metrics-reader-ca.crt
rm -f .runtime/metrics-reader-token.json

# Prometheus: separate credentials for cluster capacity metrics.
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret capacity-metrics-reader-token -o json > .runtime/capacity-reader-token.json
  if python3 scripts/internal/metrics-reader-credentials.py --capacity; then
    break
  fi
  sleep 2
done

test -s .runtime/capacity-reader.token
test -s .runtime/capacity-reader-ca.crt
setfacl -b .runtime/capacity-reader.token
chmod 600 .runtime/capacity-reader.token
setfacl -m u:65534:r-- .runtime/capacity-reader.token
chmod 644 .runtime/capacity-reader-ca.crt
rm -f .runtime/capacity-reader-token.json

# Platform API: scoped access for telemetry inspection.
for attempt in $(seq 1 30); do
  kubectl -n platform-system get secret telemetry-reviewer-token -o json > .runtime/telemetry-reviewer-token.json
  if python3 scripts/internal/kubeconfig.py --telemetry-reviewer; then
    break
  fi
  sleep 2
done

test -s .runtime/telemetry-reviewer.kubeconfig
setfacl -b .runtime/telemetry-reviewer.kubeconfig
chmod 600 .runtime/telemetry-reviewer.kubeconfig
setfacl -m u:10001:r-- .runtime/telemetry-reviewer.kubeconfig
rm -f .runtime/telemetry-reviewer-token.json

# --- Platform services and telemetry readiness ---

# Import the forwarder image before the API can schedule workload telemetry.
docker build -f platform/Dockerfile.telemetry-forwarder -t developer-platform-telemetry-forwarder:local platform
k3d image import developer-platform-telemetry-forwarder:local -c workloads

# Claim the fixed identity/API addresses before monitoring and edge containers
# can receive them from Docker's dynamic allocator. This starts only the API's
# required dependencies (PostgreSQL and the two identity initializers).
python3 scripts/checks/check-network-addresses.py
echo "Starting fixed-address identity and Platform API services first..."
docker compose up -d --build --wait --wait-timeout 180 platform-api

# The local identity issuer uses Caddy's internal CA. Export its public root
# before the isolated PostgreSQL console attempts verified OIDC discovery.
docker compose up -d proxy
python3 scripts/setup/prepare-local-trust.py

# Check fixed-address ownership again before starting the remaining services.
python3 scripts/checks/check-network-addresses.py
docker compose up -d --build --remove-orphans

# Probe Tempo from the API container to verify its internal query endpoint.
echo "Waiting for Tempo to accept queries (up to 120 seconds)..."
for attempt in $(seq 1 24); do
  if docker compose exec -T platform-api python -c 'import urllib.request; urllib.request.urlopen("http://tempo:3200/ready", timeout=3)' >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == 24 ]]; then
    echo "Tempo did not become ready." >&2
    exit 1
  fi
  sleep 5
done

echo "Waiting for the Alloy collector to become ready (up to 120 seconds)..."
docker compose up -d --no-deps --wait --wait-timeout 120 alloy

# --- Shared application access ---

# Make the authorizer image available before applying access infrastructure.
docker build -f platform/Dockerfile.access -t developer-platform-access-authorizer:local platform
k3d image import developer-platform-access-authorizer:local -c workloads
python3 scripts/setup/install-application-access.py

echo "Platform API: http://127.0.0.1:8000/docs"
