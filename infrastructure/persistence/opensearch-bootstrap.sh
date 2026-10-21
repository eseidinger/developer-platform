#!/usr/bin/env bash
set -euo pipefail

# Keep certificate-derived responses and initializer diagnostics private.
umask 077
base=/run/store-security
host=${OPENSEARCH_HOST:-opensearch}

# Wait for either a healthy catalog or a confirmed absent security index.
# An existing broken catalog requires operator repair, never reinitialization.
ready=false
for ((attempt = 1; attempt <= 90; attempt++)); do
  code=$(curl --silent --output /tmp/security-status --write-out '%{http_code}' \
    --connect-timeout 2 --max-time 4 --cacert "$base/ca.pem" \
    --cert "$base/admin.pem" --key "$base/admin-key.pem" \
    "https://$host:9200/_plugins/_security/api/internalusers" || true)
  if [[ "$code" == 200 ]]; then
    echo 'Native store access catalog already initialized; retained.'
    exit 0
  fi
  if [[ "$code" == 500 || "$code" == 503 ]]; then
    # The 3.9 API returns 500 for an absent realm. Check the actual security
    # index before initialization; a broken existing realm must not be reset.
    index_code=$(curl --silent --head --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 2 --max-time 4 --cacert "$base/ca.pem" \
      --cert "$base/admin.pem" --key "$base/admin-key.pem" \
      "https://$host:9200/.opendistro_security" || true)
    if [[ "$index_code" == 404 ]]; then
      ready=true
      break
    fi
    if [[ "$index_code" == 200 ]]; then
      echo 'Existing native store access catalog needs repair; it was not overwritten.' >&2
      exit 1
    fi
  fi
  if [[ "$code" != 000 && "$code" != 503 && "$code" != 500 ]]; then
    echo "Native store initialization status was rejected ($code)." >&2
    exit 1
  fi
  sleep 2
done

if [[ "$ready" != true ]]; then
  echo 'Native store initialization readiness timed out.' >&2
  exit 1
fi

# Initialize only the absent catalog verified above.
# The administrator certificate is mounted only into this operator initializer.
# No disabled hostname checks and no demo credentials/certificates.
/usr/share/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
  -h "$host" -p 9200 -icl -cacert "$base/ca.pem" -cert "$base/admin.pem" \
  -key "$base/admin-key.pem" -cd "$base/bootstrap" \
  > /tmp/security-init.log 2>&1 || {
  echo 'Native store initialization failed; inspect private initializer diagnostics.' >&2
  exit 1
}

echo 'Native store access catalog initialized.'
