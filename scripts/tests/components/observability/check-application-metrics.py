#!/usr/bin/env python3
"""Test production metric filters and dashboard queries in disposable Prometheus."""
import copy
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[4]
PROMETHEUS = "prom/prometheus:v3.14.0"


class Metrics(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer fixture-only":
            self.send_error(401)
            return
        now = time.monotonic()
        if self.path == "/micrometer":
            samples = [
                f'http_server_requests_seconds_count{{method="GET",status="200",uri="/private/fixture",id="request-id",user_id="fixture-user",project="foreign"}} {now * 10}',
                f'http_server_requests_seconds_count{{method="GET",status="500"}} {now * 2}',
                f'http_server_requests_seconds_sum{{method="GET",status="200"}} {now * 2}',
                f'http_server_requests_seconds_sum{{method="GET",status="500"}} {now * .4}',
                # Coexisting instrumentation must not double the generic dashboard's rate.
                f'http_requests_total{{method="GET",status="2xx"}} {now * 1000}',
                f'http_request_duration_seconds_count {now * 1000}',
                f'http_request_duration_seconds_sum {now * 900}',
                'jvm_memory_used_bytes{area="heap",id="G1 Eden Space",user_id="fixture-user"} 67108864',
                'jvm_memory_used_bytes{area="heap",id="G1 Old Gen"} 33554432',
                'jvm_memory_committed_bytes{area="heap",id="G1 Old Gen"} 134217728',
                'jvm_memory_max_bytes{area="heap",id="G1 Old Gen"} 268435456',
                'jvm_memory_used_bytes{area="nonheap",id="Metaspace"} 16777216',
                'jvm_memory_committed_bytes{area="nonheap",id="Metaspace"} 33554432',
                'jvm_memory_max_bytes{area="nonheap",id="Metaspace"} -1',
                'process_uptime_seconds 42', 'process_cpu_usage .25', 'system_cpu_usage .5',
                'jvm_threads_live_threads 10', 'jvm_threads_daemon_threads 8', 'jvm_threads_peak_threads 20',
                'jvm_threads_states_threads{state="runnable"} 6', 'jvm_threads_states_threads{state="waiting"} 4',
                f'jvm_gc_pause_seconds_count{{gc="G1 Young Generation",action="end of minor GC",cause="G1 Evacuation Pause"}} {now}',
                f'jvm_gc_pause_seconds_sum{{gc="G1 Young Generation",action="end of minor GC",cause="G1 Evacuation Pause"}} {now * .001}',
                'jvm_gc_pause_seconds_max{gc="G1 Young Generation",action="end of minor GC",cause="G1 Evacuation Pause"} .005',
                f'jvm_gc_memory_allocated_bytes_total {now * 1024}',
                f'jvm_gc_memory_promoted_bytes_total {now * 512}',
                'jvm_gc_live_data_size_bytes 33554432', 'jvm_gc_max_data_size_bytes 268435456',
                'jvm_gc_overhead .01', 'jvm_memory_usage_after_gc{pool="long-lived"} .4',
                'jvm_classes_loaded_classes 100', f'jvm_classes_unloaded_classes_total {now / 100}',
                'jvm_buffer_memory_used_bytes{id="direct"} 1024',
                'jvm_buffer_total_capacity_bytes{id="direct"} 2048', 'jvm_buffer_count_buffers{id="direct"} 2',
                'process_files_open_files 20', 'process_files_max_files 1000',
                'arbitrary_user_metric{user_id="fixture-user"} 1',
            ]
        else:
            samples = [f'http_requests_total{{method="GET",status="2xx",handler="/private/fixture",id="request-id",state="private",user_id="fixture-user"}} {now * 10}',
                       f'http_request_duration_seconds_count {now * 10}',
                       f'http_request_duration_seconds_sum {now * 3}']
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(("\n".join(samples) + "\n").encode())


def main():
    context = subprocess.check_output(["docker", "context", "show"], text=True).strip()
    endpoint = subprocess.check_output(["docker", "context", "inspect", context,
                                        "--format", "{{.Endpoints.docker.Host}}"], text=True).strip()
    if os.environ.get("DOCKER_HOST", endpoint) != "unix:///var/run/docker.sock":
        raise RuntimeError("Fixture requires the local Linux Docker socket")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Metrics)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    name = "platform-metrics-test-" + uuid.uuid4().hex[:10]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    evaluation_time = None

    def query(expression):
        parameters = {"query": expression}
        if evaluation_time is not None:
            parameters["time"] = evaluation_time
        url = f"http://127.0.0.1:{port}/api/v1/query?" + urllib.parse.urlencode(parameters)
        with urllib.request.urlopen(url, timeout=3) as response:
            return json.load(response)["data"]["result"]

    def wait_for(check):
        for _ in range(100):
            try:
                if check():
                    return
            except OSError:
                pass
            time.sleep(.2)
        raise AssertionError("Application metrics fixture did not converge")

    try:
        with tempfile.TemporaryDirectory(prefix="platform-metrics-") as directory:
            temp = Path(directory)
            temp.chmod(0o755)
            source = yaml.safe_load((ROOT / "infrastructure/monitoring/prometheus.yaml").read_text())
            job = copy.deepcopy(next(job for job in source["scrape_configs"] if job["job_name"] == "application-metrics"))
            # Only transport changes for the local fixture; production filters and limits are used verbatim.
            job.update(scheme="http", scrape_interval="1s", scrape_timeout="1s")
            job.pop("tls_config")
            job["authorization"]["credentials_file"] = "/etc/prometheus/fixture.token"
            (temp / "fixture.token").write_text("fixture-only\n")
            (temp / "discovery").mkdir()
            groups = [{"targets": [f"127.0.0.1:{server.server_port}"], "labels": {
                "project": project, "application": project, "environment": "default", "component": "web",
                "namespace": "project-" + project, "proxy_path": "/" + path}}
                for project, path in (("jvm-demo", "micrometer"), ("python-demo", "fastapi"))]
            (temp / "discovery/application-metrics.json").write_text(json.dumps(groups))
            (temp / "prometheus.yml").write_text(yaml.safe_dump({"global": {"scrape_interval": "1s"}, "scrape_configs": [job]}))
            subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "--network", "host",
                            "-v", f"{temp}:/etc/prometheus:ro", PROMETHEUS,
                            "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/tmp/data",
                            f"--web.listen-address=127.0.0.1:{port}"], check=True, stdout=subprocess.DEVNULL)
            wait_for(lambda: len(query('up{job="application-metrics"} == 1')) == 2)
            selector = 'job="application-metrics",project="jvm-demo"'
            wait_for(lambda: bool(query(f'rate(http_server_requests_seconds_count{{{selector}}}[5m])')))
            wait_for(lambda: bool(query('rate(http_requests_total{job="application-metrics",project="python-demo"}[5m])')))
            evaluation_time = time.time()

            for project in ("jvm-demo", "python-demo"):
                dashboard = json.loads((ROOT / "infrastructure/monitoring/dashboards/application-metrics.json").read_text())
                values = {}
                for panel in dashboard["panels"]:
                    expression = panel["targets"][0]["expr"].replace("$project", project).replace("$application", project).replace("$component", "web")
                    result = query(expression)
                    assert len(result) == 1, (project, panel["title"], result)
                    values[panel["title"]] = float(result[0]["value"][1])
                counter = "http_server_requests_seconds_count" if project == "jvm-demo" else "http_requests_total"
                expected = query(f'sum(rate({counter}{{job="application-metrics",project="{project}"}}[5m]))')
                assert values["Request rate"] > 0 and values["Request rate"] == float(expected[0]["value"][1]), values
                assert abs(values["Mean request duration"] - (.2 if project == "jvm-demo" else .3)) < .001, values
                if project == "python-demo":
                    assert values["Server error rate"] == 0, values
            for panel in dashboard["panels"]:
                expression = panel["targets"][0]["expr"].replace("$project", "missing").replace("$application", "missing").replace("$component", "web")
                assert not query(expression), panel["title"]
            print("PASS generic HTTP dashboard, both conventions, and Micrometer priority without double counting")

            dashboard = json.loads((ROOT / "infrastructure/monitoring/dashboards/micrometer-jvm.json").read_text())
            for panel in dashboard["panels"]:
                results = []
                for target in panel["targets"]:
                    expression = target["expr"].replace("$project", "jvm-demo").replace("$application", "jvm-demo").replace("$component", "web")
                    results.extend(query(expression))
                assert results, panel["title"]
            pools = query(f'jvm_memory_used_bytes{{{selector},area="heap"}}')
            assert len(pools) == 2 and {row["metric"]["id"] for row in pools} == {"G1 Eden Space", "G1 Old Gen"}
            threads = query(f'jvm_threads_states_threads{{{selector}}}')
            assert {row["metric"]["state"] for row in threads} == {"runnable", "waiting"}
            assert not query('arbitrary_user_metric{job="application-metrics"}')
            for row in query('{job="application-metrics",__name__=~"http_.*|jvm_.*"}'):
                labels = row["metric"]
                assert not {"uri", "handler", "user_id", "exported_project"} & labels.keys(), labels
                if labels["__name__"].startswith("http_"):
                    assert not {"id", "area", "state", "gc", "cause", "action", "pool"} & labels.keys(), labels
            assert not query('jvm_memory_used_bytes{job="application-metrics",project="python-demo"}')
            print("PASS every JVM panel query, distinct memory pools/thread states, project scoping, and label filtering")
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
