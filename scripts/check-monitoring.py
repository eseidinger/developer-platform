#!/usr/bin/env python3
"""Disposable Linux/Docker monitoring fixtures; never deploy the platform or send alerts."""
import http.server
import json
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS = "prom/prometheus:v3.14.0"
BLACKBOX = "prom/blackbox-exporter:v0.27.0"


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slow":
            time.sleep(6)
        code = 500 if self.path == "/error" else 302 if self.path == "/redirect" else 200
        if self.headers.get("Host") != "smoke.apps.localhost":
            code = 400
        self.send_response(code)
        if code == 302:
            self.send_header("Location", "/ok")
        self.end_headers()
        try:
            self.wfile.write(b"wrong application\n" if self.path == "/wrong" else b"hello-world\n")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


def main():
    context = run("docker", "context", "show").strip()
    endpoint = run("docker", "context", "inspect", context,
                   "--format", "{{.Endpoints.docker.Host}}").strip()
    # The fixture's loopback server must share the daemon's host network.
    import os
    if os.environ.get("DOCKER_HOST", endpoint) != "unix:///var/run/docker.sock":
        raise RuntimeError("Fixture requires the local Linux Docker socket")
    name = "platform-probe-test-" + uuid.uuid4().hex[:10]
    prometheus_name = name + "-prometheus"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    with tempfile.TemporaryDirectory(prefix="platform-monitoring-") as directory:
        temp = Path(directory)
        temp.chmod(0o755)
        config = ROOT / "infrastructure/monitoring"
        shutil.copy(config / "prometheus.yaml", temp / "prometheus.yml")
        shutil.copy(config / "alerts.yaml", temp / "alerts.yml")
        (temp / "discovery").mkdir()
        (temp / "discovery/applications.json").write_text("[]\n")
        print(run("docker", "run", "--rm", "--entrypoint", "/bin/promtool", "-v",
                  f"{temp}:/etc/prometheus:ro", PROMETHEUS, "check", "config", "/etc/prometheus/prometheus.yml"))
        print(run("docker", "run", "--rm", "--entrypoint", "/bin/promtool", "-v",
                  f"{config}:/work:ro", "-w", "/work", PROMETHEUS, "test", "rules", "tests/alerts.test.yaml"))
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=smoke.apps.localhost", "-keyout", str(temp / "key.pem"),
            "-out", str(temp / "cert.pem"))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(temp / "cert.pem", temp / "key.pem")
        tls_server.socket = tls.wrap_socket(tls_server.socket, server_side=True)
        for service in (server, tls_server):
            threading.Thread(target=service.serve_forever, daemon=True).start()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        try:
            run("docker", "run", "--rm", "-d", "--name", name, "--network", "host",
                "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "-v", f"{config / 'blackbox.yaml'}:/etc/blackbox.yaml:ro", BLACKBOX,
                "--config.file=/etc/blackbox.yaml", f"--web.listen-address=127.0.0.1:{port}")
            for _ in range(50):
                try:
                    with urllib.request.urlopen(base + "/-/healthy", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(run("docker", "logs", name))
            cases = [
                ("/ok", "http_status", 1), ("/ok", "http_hello_world", 1),
                ("/wrong", "http_status", 1), ("/wrong", "http_hello_world", 0),
                ("/error", "http_status", 0), ("/redirect", "http_status", 0),
                ("/slow", "http_status", 0), ("/ok", "https_status", 0),
                ("/ok", "http_hello_world", 1),
            ]
            for path, module, expected in cases:
                query = urllib.parse.urlencode({"target": f"http://127.0.0.1:{server.server_port}{path}",
                                                "module": module, "hostname": "smoke.apps.localhost"})
                with urllib.request.urlopen(base + "/probe?" + query, timeout=10) as response:
                    metrics = response.read().decode()
                assert f"probe_success {expected}\n" in metrics, (path, module, metrics)
                print(f"PASS {module} {path}: probe_success={expected}")
            query = urllib.parse.urlencode({"target": f"https://127.0.0.1:{tls_server.server_port}/ok",
                                            "module": "https_hello_world", "hostname": "smoke.apps.localhost"})
            with urllib.request.urlopen(base + "/probe?" + query, timeout=10) as response:
                assert "probe_success 0\n" in response.read().decode()
            print("PASS untrusted TLS certificate rejected")
            # Use the actual discovery generator and relabel configuration in a real Prometheus.
            import sys
            sys.path.insert(0, str(ROOT / "platform"))
            from app.monitoring import atomic_write, target_groups
            groups = target_groups([
                ("smoke", {"probe_profile": "hello-world"}, "applied"),
                ("broken", {}, "failed"),
            ], "apps.localhost")
            for group in groups:
                group["targets"] = [f"http://127.0.0.1:{server.server_port}/" +
                                    ("ok" if group["labels"]["project"] == "smoke" else "error")]
            atomic_write(temp / "discovery/applications.json", json.dumps(groups))
            configuration = (temp / "prometheus.yml").read_text()
            configuration = configuration.replace("scrape_interval: 30s", "scrape_interval: 1s\n  scrape_timeout: 1s")
            configuration = configuration.replace("refresh_interval: 15s", "refresh_interval: 1s")
            configuration = configuration.replace("scrape_timeout: 10s", "scrape_timeout: 1s")
            configuration = configuration.replace("blackbox-exporter:9115", f"127.0.0.1:{port}")
            configuration = configuration.replace("alertmanager:9093", "127.0.0.1:9")
            (temp / "prometheus.yml").write_text(configuration)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                prom_port = sock.getsockname()[1]
            run("docker", "run", "--rm", "-d", "--name", prometheus_name, "--network", "host",
                "-v", f"{temp}:/etc/prometheus:ro", PROMETHEUS,
                "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/tmp/data",
                f"--web.listen-address=127.0.0.1:{prom_port}")
            def query(expression):
                url = f"http://127.0.0.1:{prom_port}/api/v1/query?" + urllib.parse.urlencode({"query": expression})
                with urllib.request.urlopen(url, timeout=2) as response:
                    return json.load(response)["data"]["result"]
            def wait_for(check):
                for _ in range(100):
                    try:
                        if check():
                            return
                    except (OSError, KeyError):
                        pass
                    time.sleep(0.2)
                raise AssertionError("Prometheus discovery did not converge: " + run("docker", "logs", prometheus_name))
            wait_for(lambda: len(query('probe_success{job="applications"}')) == 2)
            values = {r["metric"]["application"]: r["value"][1]
                      for r in query('probe_success{job="applications"}')}
            assert values == {"smoke": "1", "broken": "0"}, values
            print("PASS generated targets, hostname routing, module selection and application labels")
            atomic_write(temp / "discovery/applications.json", json.dumps([
                group for group in groups if group["labels"]["application"] != "smoke"]))
            wait_for(lambda: len(query('probe_success{job="applications"}')) == 1)
            remaining = query('probe_success{job="applications"}')
            assert remaining[0]["metric"]["application"] == "broken"
            print("PASS discovery removes retired target without restarting Prometheus; failed target remains")

        finally:
            subprocess.run(["docker", "rm", "-f", prometheus_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for service in (server, tls_server):
                service.shutdown()
                service.server_close()


if __name__ == "__main__":
    main()
