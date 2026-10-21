#!/usr/bin/env python3
"""Disposable production Alloy metric pipeline -> Prometheus fixture.

No live containers/configuration/data touched. Requires Docker and Python stdlib.
"""
import json
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=15).strip()


def request(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=3))


def wait(callback, seconds=35):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = callback()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise AssertionError("Fixture readiness/query timeout")


def main():
    suffix = uuid4().hex[:10]
    prom, alloy = "ai-prom-" + suffix, "ai-alloy-" + suffix
    with tempfile.TemporaryDirectory(prefix="ai-metric-pipeline-") as directory:
        tmp = Path(directory)
        tmp.chmod(0o755)
        (tmp / "prom.yml").write_text('global:\n  scrape_interval: 5s\nscrape_configs:\n  - job_name: alloy\n    static_configs:\n      - targets: [127.0.0.1:12345]\n')
        source = (ROOT / "infrastructure/monitoring/config.alloy").read_text()
        config = source[source.index('// Private platform spans'):].replace(
            'http://prometheus:9090/api/v1/otlp', 'http://127.0.0.1:9090/api/v1/otlp')
        (tmp / "config.alloy").write_text(config)
        try:
            run("docker", "run", "-d", "--name", prom, "--network", "none", "--memory", "256m",
                "-v", f"{tmp}/prom.yml:/etc/prometheus/prometheus.yml:ro", "prom/prometheus:v3.14.0",
                "--config.file=/etc/prometheus/prometheus.yml", "--web.enable-otlp-receiver")
            # Share only this disposable network namespace, with no external network.
            run("docker", "run", "-d", "--name", alloy, "--network", "container:" + prom,
                "--memory", "256m", "-v", f"{tmp}/config.alloy:/etc/alloy/config.alloy:ro",
                "grafana/alloy:v1.19.2", "run", "/etc/alloy/config.alloy")
            # Use the container's bash TCP client to inject HTTP without publishing ports.
            now = int(run("docker", "exec", prom, "date", "+%s")) * 1_000_000_000
            def metric(name):
                return {"name": name, "sum": {"aggregationTemporality": 2, "isMonotonic": True,
                    "dataPoints": [{"startTimeUnixNano": str(now - 1_000_000), "timeUnixNano": str(now),
                        "asDouble": 7, "attributes": [{"key": "project", "value": {"stringValue": "lab"}},
                            {"key": "password", "value": {"stringValue": "seed-private-marker"}}]}]}}
            payload = json.dumps({"resourceMetrics": [{"resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "platform-api"}},
                {"key": "secret", "value": {"stringValue": "seed-private-marker"}}]},
                "scopeMetrics": [{"metrics": [metric("platform_ai_runs"), metric("unreviewed_secret_metric")]}]}]})
            http = f'POST /v1/metrics HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n{payload}'
            def inject():
                result = subprocess.run(["docker", "exec", "-i", alloy, "/usr/bin/bash", "-c",
                    'exec 3<>/dev/tcp/127.0.0.1/4318; cat >&3; cat <&3'], input=http, text=True, capture_output=True, timeout=5)
                if result.returncode == 0 and "200 OK" in result.stdout:
                    return True
                return False
            wait(inject)
            def query(expression):
                result = run("docker", "exec", prom, "wget", "-T", "3", "-qO-",
                    "http://127.0.0.1:9090/api/v1/query?query=" + urllib.parse.quote(expression))
                return json.loads(result)["data"]["result"]
            try:
                observed = wait(lambda: query("platform_ai_runs_total"))
            except AssertionError:
                print(run("docker", "logs", "--tail", "55", alloy))
                print(run("docker", "logs", "--tail", "10", prom))
                print("Available metric names:", query('{__name__=~"platform_ai_.*"}'))
                raise
            assert len(observed) == 1 and float(observed[0]["value"][1]) == 7, observed
            assert observed[0]["metric"]["project"] == "lab"
            assert "seed-private-marker" not in json.dumps(observed)
            assert "password" not in observed[0]["metric"] and "secret" not in observed[0]["metric"]
            assert not query("unreviewed_secret_metric_total")
            # Parse all provisioned AI PromQL targets against the real pinned engine.
            count = 0
            for path in (ROOT / "infrastructure/monitoring/dashboards").glob("ai-*.json"):
                dashboard = json.loads(path.read_text())
                for panel in dashboard["panels"]:
                    for target in panel["targets"]:
                        expr = target["expr"]
                        for variable in ("project", "action", "provider", "model"):
                            expr = expr.replace("$" + variable, ".*")
                        expr = expr.replace("$__range", "1h")
                        if panel["title"] == "Metric export queue":
                            queue = wait(lambda: query(expr))
                            assert len(queue) == 1 and queue[0]["metric"]["data_type"] == "metrics", queue
                        else:
                            query(expr)
                        count += 1
            print(f"PASS direct OTLP -> production Alloy filter/translation -> Prometheus: value=7; private labels and unreviewed metric dropped; {count} dashboard queries parsed")
        finally:
            for name in (alloy, prom):
                subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)


if __name__ == "__main__":
    main()
