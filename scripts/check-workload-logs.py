#!/usr/bin/env python3
"""Disposable Alloy/Loki + fake Kubernetes API fixture; never deploy the platform.

Exercises the *production* discovery, Kubernetes log source and minimization
pipeline. Configured seven-day retention is not a seven-day elapsed-time drill.
"""
import http.server
import json
import logging
import shlex
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALLOY = "grafana/alloy:v1.19.2"
LOKI = "grafana/loki:3.7.8"
CORRELATION = "a" * 32
OPERATION = "12345678-1234-1234-1234-123456789abc"

# Exercise real framework schemas, escaping, MDC correlation and input rejection.
FRAMEWORK_LOGS = [
    {"timestamp": "ignored-app-clock", "level": "WARNING", "loggerName": "org.acme.Service",
     "message": 'Ready "now"\nGrüße', "mdc": {"traceId": "A" * 32, "spanId": "B" * 16},
     "password": "MUST-NOT-STORE", "stackTrace": "MUST-NOT-STORE"},
    {"@timestamp": "ignored-app-clock", "level": "INFO", "logger_name": "com.example.Web",
     "message": "token=MUST-NOT-STORE Authorization: Bearer MUST-NOT-STORE", "trace_id": "c" * 32,
     "span_id": "d" * 16, "headers": {"cookie": "MUST-NOT-STORE"}},
    {"level": "ERROR", "message": "invalid optional IDs are discarded", "traceId": "0" * 32,
     "spanId": "invalid", "loggerName": {"secret": "MUST-NOT-STORE"}},
]
INVALID_LOGS = [
    {"level": "INFO", "message": "token=x " * 200},
    {"level": "INFO", "message": {"secret": "MUST-NOT-STORE"}},
    {"level": ["INFO"], "message": "MUST-NOT-STORE"},
    {"level": "INFO", "message": "MUST-NOT-STORE" + "x" * 2000},
    {"level": "unknown", "message": "MUST-NOT-STORE"},
    {"level": "INFO", "message": "MUST-NOT-STORE", "event": "invalid"},
]


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def collector_runtime(service, volume):
    """Use production identity, state mount, hardening and readiness settings."""
    assert service["read_only"]
    assert "alloy:/var/lib/alloy" in service["volumes"]
    args = ["--user", service["user"], "--memory", service["mem_limit"], "--read-only",
            "-v", volume + ":/var/lib/alloy"]
    for mount in service["tmpfs"]:
        args += ["--tmpfs", mount]
    for capability in service["cap_drop"]:
        args += ["--cap-drop", capability]
    for option in service["security_opt"]:
        args += ["--security-opt", option]
    health = service["healthcheck"]
    assert health["test"][0] == "CMD"
    args += ["--health-cmd", shlex.join(health["test"][1:]).replace("$$", "$"),
             "--health-interval", health["interval"], "--health-timeout", health["timeout"],
             "--health-start-period", health["start_period"], "--health-retries", str(health["retries"])]
    return args


def wait_collector(container, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = json.loads(run("docker", "inspect", "--format", "{{json .State}}", container))
        if state.get("Health", {}).get("Status") == "healthy":
            return
        if not state["Running"] or state.get("Health", {}).get("Status") == "unhealthy":
            break
        time.sleep(1)
    raise AssertionError("Collector failed production readiness check: " + run("docker", "logs", "--tail", "20", container))


def pod(namespace, name, component):
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {
        "namespace": namespace, "name": name, "uid": str(uuid4()), "resourceVersion": "1",
        "labels": {"app.kubernetes.io/name": "demo", "platform.example/component": component},
        "annotations": {"platform.example/revision": "1", "platform.example/operation-id": OPERATION}},
        "spec": {"nodeName": "test-node", "containers": [{"name": component, "image": "example.invalid/test"}]},
        "status": {"phase": "Running", "podIP": "127.0.0.1", "containerStatuses": [{"name": component,
            "ready": True, "restartCount": 0, "image": "example.invalid/test", "imageID": "test",
            "containerID": "test", "state": {"running": {"startedAt": "2026-10-11T00:00:00Z"}}}]}}


class Kubernetes(http.server.BaseHTTPRequestHandler):
    pods = [pod("project-demo", "api-123", "api"), pod("project-demo", "worker-123", "worker"),
            pod("platform-system", "must-not-collect", "system")]
    log_paths = set()
    request_paths = set()

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path)
        self.request_paths.add(self.path)
        query = urllib.parse.parse_qs(path.query)
        if self.headers.get("Authorization") != "Bearer disposable-test-only":
            self.send_error(401)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            if path.path == "/version":
                self.wfile.write(json.dumps({"major": "1", "minor": "36", "gitVersion": "v1.36.5"}).encode())
            elif path.path.endswith("/log"):
                self.log_paths.add(path.path)
                timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                lines = [json.dumps({"event": "request.completed", "level": "info", "correlationId": CORRELATION,
                                     "token": "MUST-NOT-STORE", "customer": "MUST-NOT-STORE"}),
                         'raw token=MUST-NOT-STORE', 'not-json', 'null', 'true', '42',
                         '["MUST-NOT-STORE"]', '"MUST-NOT-STORE"',
                         '{"event":"request.failed","level":"error","correlationId":"MUST-NOT-STORE"}']
                lines += [json.dumps(record) for record in FRAMEWORK_LOGS + INVALID_LOGS]
                self.wfile.write("".join(timestamp + " " + line + "\n" for line in lines).encode())
            elif query.get("watch") == ["true"]:
                for item in self.pods:
                    self.wfile.write((json.dumps({"type": "ADDED", "object": item}) + "\n").encode())
                # New client-go uses watch-list initialization: a bookmark ends
                # the initial event set before discovery becomes synchronized.
                self.wfile.write((json.dumps({"type": "BOOKMARK", "object": {"apiVersion": "v1", "kind": "Pod",
                    "metadata": {"resourceVersion": "1", "annotations": {"k8s.io/initial-events-end": "true"}}}}) + "\n").encode())
                self.wfile.flush()
                time.sleep(1)
            elif "/pods/" in path.path:
                item = next(item for item in self.pods if item["metadata"]["name"] == path.path.rsplit("/", 1)[1])
                self.wfile.write(json.dumps(item).encode())
            else:
                self.wfile.write(json.dumps({"apiVersion": "v1", "kind": "PodList",
                    "metadata": {"resourceVersion": "1"}, "items": self.pods}).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    context = run("docker", "context", "show").strip()
    endpoint = run("docker", "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}").strip()
    import os
    if os.environ.get("DOCKER_HOST", endpoint) != "unix:///var/run/docker.sock":
        raise RuntimeError("Fixture requires the local Linux Docker socket")
    name = "platform-log-test-" + uuid4().hex[:10]
    names = [name + "-loki", name + "-alloy"]
    state_volume = name + "-alloy-state"
    service = yaml.safe_load((ROOT / "infrastructure/monitoring/compose.yaml").read_text())["services"]["alloy"]
    assert service["image"] == ALLOY
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Kubernetes)
    with tempfile.TemporaryDirectory(prefix="platform-workload-logs-") as directory:
        work = Path(directory)
        work.chmod(0o755)
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
            "-keyout", str(work / "key.pem"), "-out", str(work / "cert.pem"))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(work / "cert.pem", work / "key.pem")
        api.socket = tls.wrap_socket(api.socket, server_side=True)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        loki_port, alloy_port = free_port(), free_port()
        loki_url = "http://127.0.0.1:" + str(loki_port)
        config = (ROOT / "infrastructure/monitoring/config.alloy").read_text()
        # Only transport paths/addresses change; production filters/stages intact.
        config = config.replace("/run/alloy/log-reader.kubeconfig", "/work/log-reader.kubeconfig")
        config = config.replace("http://loki:3100", loki_url)
        (work / "config.alloy").write_text(config)
        (work / "log-reader.kubeconfig").write_text(json.dumps({
            "apiVersion": "v1", "kind": "Config", "current-context": "fixture",
            "clusters": [{"name": "fixture", "cluster": {"server": "https://127.0.0.1:" + str(api.server_port),
                                                        "certificate-authority": "/work/cert.pem"}}],
            "users": [{"name": "fixture", "user": {"token": "disposable-test-only"}}],
            "contexts": [{"name": "fixture", "context": {"cluster": "fixture", "user": "fixture"}}]}))
        # Disposable fake token only; accommodates Docker user-namespace remapping.
        (work / "log-reader.kubeconfig").chmod(0o644)
        loki = (ROOT / "infrastructure/monitoring/loki.yaml").read_text().replace("http_listen_port: 3100", "http_listen_port: " + str(loki_port))
        loki = loki.replace("http_listen_port: " + str(loki_port),
                            "http_listen_port: " + str(loki_port) + "\n  grpc_listen_port: " + str(free_port()))
        (work / "loki.yaml").write_text(loki)
        try:
            # Docker populates a fresh named volume from the pinned image's
            # 473:473/0770 directory. Reproduce the old UID 0/GID 0 failure.
            denied = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only",
                "--user", "0", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "-v", state_volume + ":/var/lib/alloy", "--entrypoint", "/usr/bin/bash", ALLOY,
                "-ec", "test -w /var/lib/alloy"], capture_output=True, text=True)
            assert denied.returncode == 1, "Old collector identity unexpectedly has state write access"
            run("docker", "run", "--rm", "-v", f"{work}:/work:ro", ALLOY, "validate", "/work/config.alloy")
            run("docker", "run", "-d", "--name", names[0], "--network", "host",
                "-v", f"{work}:/work:ro", LOKI, "-config.file=/work/loki.yaml")
            # Keep the production state path and a real named volume; only the
            # transport port differs in this disposable host-network fixture.
            runtime = collector_runtime(service, state_volume)
            runtime = [arg.replace("127.0.0.1/12345", "127.0.0.1/" + str(alloy_port)) for arg in runtime]
            run("docker", "run", "-d", "--name", names[1], "--network", "host", *runtime,
                "-v", f"{work}:/work:ro", ALLOY, "run", "/work/config.alloy",
                "--storage.path=/var/lib/alloy", "--server.http.listen-addr=127.0.0.1:" + str(alloy_port))
            wait_collector(names[1])
            run("docker", "exec", names[1], "/usr/bin/bash", "-ec", "test -d /var/lib/alloy/remotecfg")
            run("docker", "restart", names[1])
            wait_collector(names[1])
            print("PASS production collector identity, persistent state permissions, hardening, readiness and restart")
            def query():
                params = urllib.parse.urlencode({"query": '{job="kubernetes-workloads"}', "limit": 100})
                with urllib.request.urlopen(loki_url + "/loki/api/v1/query_range?" + params, timeout=3) as response:
                    return json.load(response)["data"]["result"]
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                try:
                    streams = query()
                    if len(streams) >= 4 and sum(len(item["values"]) for item in streams) >= 8:
                        break
                except (OSError, KeyError):
                    pass
                time.sleep(0.5)
            else:
                raise AssertionError("Central log ingestion did not converge; requests=" + str(Kubernetes.request_paths)
                                     + "; log paths=" + str(Kubernetes.log_paths)
                                     + run("docker", "logs", "--tail", "30", names[1])
                                     + run("docker", "logs", "--tail", "10", names[0]))
            assert {item["stream"]["component"] for item in streams} == {"api", "worker"}
            assert all(item["stream"]["project"] == "demo" for item in streams)
            assert not any("platform-system" in path for path in Kubernetes.log_paths)
            assert "MUST-NOT-STORE" not in json.dumps(streams)
            params = urllib.parse.urlencode({"match[]": '{job="kubernetes-workloads"}'})
            with urllib.request.urlopen(loki_url + "/loki/api/v1/series?" + params, timeout=3) as response:
                indexed = json.load(response)["data"]
            assert indexed and all("operation_id" not in item and "revision" not in item for item in indexed)
            import sys
            sys.path.insert(0, str(ROOT / "platform" / "app" / "src"))
            for item in streams:
                for entry in item["values"]:
                    record = json.loads(entry[1])
                    from app.retained_logs import safe_log_record
                    assert safe_log_record(entry[1]) == record
                    if "event" in record:
                        assert record == {"event": "request.completed", "level": "info", "correlationId": CORRELATION}
                    elif record["message"].startswith('Ready "now"'):
                        assert record == {"format": "application-json-v1", "level": "warning",
                                          "message": 'Ready "now"\nGrüße', "logger": "org.acme.Service",
                                          "traceId": "a" * 32, "spanId": "b" * 16}
                    elif record["message"].startswith("token="):
                        assert record["message"] == "token=[REDACTED] Authorization=[REDACTED] [REDACTED]"
                        assert record["logger"] == "com.example.Web" and record["traceId"] == "c" * 32
                    else:
                        assert record == {"format": "application-json-v1", "level": "error",
                                          "message": "invalid optional IDs are discarded"}
                    metadata = entry[2] if len(entry) > 2 else item["stream"]
                    assert metadata["operation_id"] == OPERATION and metadata["revision"] == "1"
            for component in ("api", "worker"):
                records = [json.loads(entry[1]) for item in streams if item["stream"]["component"] == component
                           for entry in item["values"]]
                assert {record.get("logger", record.get("event", record.get("message"))) for record in records} == {
                    "org.acme.Service", "com.example.Web", "request.completed", "invalid optional IDs are discarded"}
            print("PASS production Kubernetes discovery/source, component labels, framework JSON, safe envelopes, redaction, trace IDs and non-indexed operation metadata")
            import sys
            sys.path.insert(0, str(ROOT / "platform" / "app" / "src"))
            from app.retained_logs import observe_retained_logs
            previous_url = os.environ.get("LOKI_URL")
            os.environ["LOKI_URL"] = loki_url
            try:
                result = observe_retained_logs("demo", logging.getLogger("fixture"), component="api")
                assert result["state"] == "ok" and result["lines"][0]["operation_id"] == OPERATION
                retained_timestamps = {line["timestamp"] for line in result["lines"]}
                # Stop new ingestion so post-restart success cannot be a new log
                # replacing missing persisted data with the same event/correlation.
                run("docker", "stop", names[1])
                run("docker", "restart", names[0])
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    result = observe_retained_logs("demo", logging.getLogger("fixture"), component="api")
                    if result["state"] == "ok" and retained_timestamps <= {line["timestamp"] for line in result["lines"]}:
                        break
                    time.sleep(1)
                assert result["state"] == "ok" and retained_timestamps <= {line["timestamp"] for line in result["lines"]}
                print("PASS scoped retained-log reader and Loki restart readback (seven-day elapsed retention remains live acceptance)")
            finally:
                if previous_url is None:
                    os.environ.pop("LOKI_URL", None)
                else:
                    os.environ["LOKI_URL"] = previous_url
        finally:
            for container in reversed(names):
                subprocess.run(["docker", "rm", "-f", "-v", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Exact UUID-scoped fixture volume only; never remove platform data.
            subprocess.run(["docker", "volume", "rm", state_volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            api.shutdown()
            api.server_close()


if __name__ == "__main__":
    main()
