# Platform trace bootstrap

The platform API emits explicit, sampled spans to the private Alloy listener.
Alloy removes unapproved resource and span attributes before forwarding to
Tempo. The Grafana Tempo data source is operator-only. No hosted workload is
authorized to send traces yet; that requires the workload identity gateway.

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

`PLATFORM_TRACE_SAMPLE_RATE` sets the root probability from 0 to 1 and defaults
to 0.1. Change it in `.env`, then recreate `platform-api` through the normal
controlled deployment. An initiating sampled API request records a W3C context
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
three GiB, and actual 24-hour compaction. The disk image protects the host at
four GiB; automatic admission stop at three GiB is still pending.
