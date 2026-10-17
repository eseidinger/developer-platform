# Platform trace bootstrap

The platform API emits explicit, sampled spans to the private Alloy listener.
Alloy removes unapproved platform span attributes before forwarding to Tempo.
The Grafana Tempo data source is operator-only. Opted-in hosted workloads send
to a Pod-local OTLP forwarder at `127.0.0.1:4318`; it reads the rotating
Pod-bound token for every batch and sends to the dedicated private gateway.
Only the forwarder mounts the token. The gateway checks the current Pod and
catalog opt-in, then rewrites the batch to a small allowlist. A failed exporter
or gateway must not block application requests.

On the lab host, prepare the dedicated four GiB filesystem before running
`scripts/up.sh`:

```bash
sudo bash scripts/prepare-tempo-storage.sh
bash scripts/up.sh
```

Run the preparation command again after a host reboot, before starting the
Compose stack. The image and mount live in `/var/lib/developer-platform`,
outside the source checkout and platform backup. Tempo retains blocks for 24
hours; this is configuration, not proof that elapsed deletion has occurred.
The same bounded filesystem is mounted at `/data/tempo` and `/var/tempo` inside
Tempo; Tempo 3 writes live-store runtime files under the latter path. Bootstrap
waits for Tempo's `/ready` endpoint before reporting success.
The remote Ansible deployment transfers the script and prepares the mount
before starting Compose. Bootstrap keeps Kubernetes bearer credentials owner
only and grants read access by UID-specific ACL to the API, Alloy, Prometheus,
and telemetry gateway as needed. The host needs the `acl` package; the
deployment playbook installs it.

`PLATFORM_TRACE_SAMPLE_RATE` sets the root probability from 0 to 1 and defaults
to 1.0 (100%). Change it in `.env`, then recreate `platform-api` and
reconcile hosted-application access gateways and tracing-enabled workloads through
the normal controlled deployment. Existing gateways and Pods retain their old
environment until recreated/reconciled. The 100% default samples every eligible
root; queue/ingest limits, backend outages and retention can still lose spans. An initiating sampled API request records a W3C context
with its durable operation; a worker retry creates a new trace with an origin
link. The response header `X-Platform-Trace-Id` is diagnostic and grants no
read access. Raw trace search remains operator-only.

The current source checks are:

```bash
docker compose config --no-interpolate --quiet
docker run --rm -v "$PWD/infrastructure/monitoring/config.alloy:/etc/alloy/config.alloy:ro" \
  grafana/alloy:v1.19.2 validate /etc/alloy/config.alloy
```

Before accepting deployed tracing, measure the 100% fixture rate, verify
end-to-end readback and rejection behavior, resource cost, disk admission at
three GiB, and actual 24-hour compaction. The gateway stops workload ingress
at three GiB until usage falls below two GiB. The dedicated filesystem caps
total trace data at four GiB. The platform API's own exporter bypasses the
gateway and is still subject to Tempo's ingest limit and filesystem cap.

## Hosted application setup

Declare `spec.components[].telemetry.tracing.enabled: true` in a `v1alpha2`
application. The platform supplies a localhost OTLP HTTP/protobuf endpoint,
stable `OTEL_SERVICE_NAME`, parent-based sampler settings, and the forwarder.
The app must include framework instrumentation and export traces as
HTTP/protobuf. The collector stores only its safe allowlist; applications
should still avoid recording sensitive span data before export. Request
context uses W3C `traceparent`; pass it through normal instrumented HTTP
clients for in-project calls.

| Framework | Instrumentation | Metrics declaration |
|---|---|---|
| Spring Boot | Add `spring-boot-starter-opentelemetry`; Boot maps supported OTel environment settings and uses parent-based sampling. Build outbound clients with auto-configured builders to propagate context. See [Spring tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) and [OTel environment mapping](https://docs.spring.io/spring-boot/reference/actuator/observability.html). | Add Actuator and `micrometer-registry-prometheus`, expose `/actuator/prometheus`, and declare that private port/path. See [Spring metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html). |
| Quarkus | Add `quarkus-opentelemetry`. The platform also supplies Quarkus-specific OTLP HTTP endpoint/protocol variables. Keep W3C trace context propagation and parent-based sampling. See [Quarkus OpenTelemetry](https://quarkus.io/guides/opentelemetry/). | Add `quarkus-micrometer-registry-prometheus`, expose `/q/metrics` privately, and declare that port/path. See [Quarkus Micrometer](https://quarkus.io/guides/telemetry-micrometer/). |
| FastAPI | Install `opentelemetry-distro` and `opentelemetry-exporter-otlp-proto-http`, run `opentelemetry-bootstrap -a install`, then launch through `opentelemetry-instrument`. Its OTLP environment settings use the platform localhost endpoint. See [Python zero-code instrumentation](https://opentelemetry.io/docs/zero-code/python/) and [OTLP exporters](https://opentelemetry.io/docs/languages/python/exporters/). | Expose a Prometheus request/error/latency endpoint on a declared private port/path. The shared Application metrics dashboard supports the default `prometheus-fastapi-instrumentator` HTTP counters and durations. |

The forwarder image is built and imported into k3d by `scripts/up.sh` before
the Platform API starts. It adds 25m CPU/64 MiB requests and 100m CPU/128 MiB
limits per opted-in Pod; project quota and optional cluster admission include
these amounts. The local endpoint is trace-only; application metric scraping
uses the separate declaration and private proxy.

Scheduled components run the forwarder as a native sidecar (`initContainers`
with `restartPolicy: Always`) on the pinned Kubernetes version. Kubernetes stops
it when the main job container finishes, allowing successful jobs to complete
and failed jobs to report their exit status without waiting for the deadline.
