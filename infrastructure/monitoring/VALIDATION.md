# Monitoring validation

See the [monitoring directory guide](README.md) for configuration ownership and
related contracts. Run commands from the repository root.

## Local preparation and validation

Install the root `requirements.txt` for YAML linting. These checks read source
configuration without starting platform services:

```bash
yamllint infrastructure
python3 scripts/generate/generate-dashboards.py --check
docker compose --profile '*' config --quiet
```

Use the service versions pinned in `compose.yaml` for native checks. The rule
fixtures need temporary scratch space, but mount the source read-only:

```bash
docker run --rm --network none --entrypoint /bin/promtool \
  -v "$PWD/infrastructure/monitoring:/work:ro" -w /work \
  prom/prometheus:v3.14.0 test rules \
  tests/alerts.test.yaml tests/capacity.test.yaml \
  tests/stores.test.yaml tests/native-stores.test.yaml

docker run --rm --network none \
  -v "$PWD/infrastructure/monitoring:/work:ro" \
  grafana/alloy:v1.19.2 fmt --test /work/config.alloy

docker run --rm --network none \
  -v "$PWD/infrastructure/proxy:/work:ro" \
  caddy:2.11.4-alpine caddy fmt --diff /work/Caddyfile
```

Folded YAML blocks make PromQL, SQL, and shell commands readable across lines.
Regular expressions and paths use escaped line continuations where adding a
space would change their value. Preserve that distinction when editing them.

Install test dependencies in a virtual environment, then run:

```bash
uv sync --project platform/app
uv run --project platform/app python -m unittest discover -s platform/app/tests -v
python3 scripts/tests/components/observability/check-monitoring.py
python3 scripts/tests/components/observability/check-workload-logs.py
docker compose config --quiet
```

The fixture script requires Linux Docker on the local Unix socket and OpenSSL.
It starts temporary loopback HTTP/TLS servers, a blackbox exporter and
Prometheus, then removes those containers. It validates production
configuration/rules, status, content, redirect, timeout, certificate rejection,
recovery, target labels and live discovery removal. The workload-log fixture
uses real pinned Alloy/Loki and a TLS-verified fake Kubernetes API to verify
discovery/source, safe ingestion, scope, structured metadata and Loki restart
readback. It reproduces the old UID/GID permission failure, then uses production
hardening and a fresh named state volume at `/var/lib/alloy` to verify collector
readiness and restart. Both remove their containers (and the workload fixture's
exact temporary volume), never deploy the platform and send no notifications.
Neither proves seven elapsed days of retention or real-cluster behavior. API
lifecycle tests use simulated PostgreSQL/Kubernetes dependencies; they do not
establish real cluster deletion or notification delivery.

For a fresh local platform, follow the
[quick start](../../README.md#quick-start). For an existing installation, after
other drills finish and with no provisioning request in progress, deploy the
changed source and recreate the affected services:

```bash
bash scripts/up.sh
```

The exporter has no published host port. In Prometheus at
`http://localhost:9090`, check Targets and query
`probe_success{job="applications"}`. For protected components, also inspect
Kubernetes readiness; a successful boundary denial is not workload health. Check
`platform_discovery_last_success_timestamp_seconds` and confirm labels identify
the intended application. Retained discovery volumes rebuild from the current
catalog at API startup; a fresh empty catalog publishes an empty target list.

The volume is disposable derived state. Project specs (including profiles) and
retired status remain in the existing PostgreSQL backup; source includes
exporter and alert configuration. No additional secret or independent backup of
discovery files is needed. A restore rebuilds them against the restored
installation's `APPS_DOMAIN`. Explicitly selecting a retired project for
restore/reapply via PUT reactivates it; automatic bulk reapply should skip
retired catalog entries.

## Live acceptance still required

Previously recorded checks and their limits are retained in the
[verification history](VERIFICATION-HISTORY.md#hosted-access-monitoring).

Use the neutral hosted-access harness with `--monitoring` and a newly published
fixture digest. It verifies component URLs/probes, Kubernetes readiness and safe
provider/consumer central correlation before retirement. It does not remove the
full monitoring/retention deferral: record an operational event, confirm
readback after pod retirement/restart, and verify retention around the seven-day
boundary including compactor deletion delay. Record collector/backend health and
gaps. Keep PLAN-017 open until the remaining readback and retention acceptance
are recorded.

After the backup drills finish, verify the public smoke probe, then temporarily
scale its deployment to zero and confirm the application alert reaches the
intended inbox. Restore the original replica count and confirm readiness, the
successful probe, and the recovery email. Record revision, target, original
replicas, failure/recovery and receipt times. Test retirement separately on an
intentionally disposable application. Local fixtures do not close OPS-007-T01.
