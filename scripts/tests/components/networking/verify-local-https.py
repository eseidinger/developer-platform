#!/usr/bin/env python3
"""Exercise the production local HTTPS gateway in an isolated Docker fixture.

The synthetic upstream accepts everything, so denied requests prove the gateway
boundary. This test neither deploys the platform nor uses real credentials.
"""

import http.client
import os
import socket
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
CERTIFICATE = "/data/caddy/pki/authorities/local/root.crt"
BACKEND = """
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'synthetic-upstream')
    def log_message(self, *args):
        pass
Thread(target=ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever).start()
ThreadingHTTPServer(('0.0.0.0',80),Handler).serve_forever()
"""


def command(*arguments, check=True):
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=60, check=False
    )
    if check and result.returncode:
        raise RuntimeError("Disposable gateway command failed")
    return result


def wait_ready(
    request, host, path, *, seconds=20, clock=time.monotonic, sleep=time.sleep
):
    """The CA is written before Caddy finishes activating its TLS listeners."""
    deadline = clock() + seconds
    while clock() < deadline:
        try:
            if request(host, path) == 200:
                return
        except (OSError, http.client.HTTPException):
            pass
        sleep(0.25)
    raise AssertionError("Gateway verified HTTPS readiness timed out")


def main():
    context = command("context", "show").stdout.strip()
    endpoint = command(
        "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"
    ).stdout.strip()
    if os.environ.get("DOCKER_HOST", endpoint) != "unix:///var/run/docker.sock":
        raise RuntimeError("Fixture requires the local Linux Docker socket")
    name = "local-https-fixture-" + uuid4().hex[:12]
    backend, gateway = name + "-backend", name + "-gateway"
    command("network", "create", name)
    try:
        with tempfile.TemporaryDirectory(prefix=name) as directory:
            target = Path(directory)
            target.chmod(0o755)
            config = target / "Caddyfile"
            config.write_text(
                (ROOT / "infrastructure/proxy/Caddyfile.workloads").read_text()
            )
            config.chmod(0o644)
            command(
                "run",
                "-d",
                "--name",
                backend,
                "--network",
                name,
                "--network-alias",
                "keycloak",
                "--network-alias",
                "k3d-workloads-serverlb",
                "--memory",
                "64m",
                "python:3.14.7-slim-trixie",
                "python",
                "-c",
                BACKEND,
            )
            command(
                "run",
                "-d",
                "--name",
                gateway,
                "--network",
                name,
                "--memory",
                "128m",
                "-p",
                "127.0.0.1::443",
                "-e",
                "IDENTITY_DOMAIN=identity.localhost",
                "-e",
                "APPS_DOMAIN=apps.localhost",
                "-v",
                f"{config}:/etc/caddy/Caddyfile:ro",
                "caddy:2.11.4-alpine",
            )
            port = int(
                command("port", gateway, "443/tcp").stdout.strip().rsplit(":", 1)[1]
            )
            certificate = ""
            for _ in range(40):
                result = command("exec", gateway, "cat", CERTIFICATE, check=False)
                if not result.returncode:
                    certificate = result.stdout
                    break
                time.sleep(0.25)
            if not certificate:
                raise AssertionError("Gateway certificate readiness timed out")
            tls = ssl.create_default_context(cadata=certificate)

            def request(host, path, host_header=None):
                connection = http.client.HTTPSConnection(
                    host, port, timeout=5, context=tls
                )
                try:
                    connection.sock = tls.wrap_socket(
                        socket.create_connection(("127.0.0.1", port), timeout=5),
                        server_hostname=host,
                    )
                    connection.request(
                        "GET", path, headers={"Host": host_header or host}
                    )
                    response = connection.getresponse()
                    response.read()
                    return response.status
                finally:
                    connection.close()

            # Warm both certificate/routing paths with verified positive
            # controls. Once ready, every denial below remains a strict check.
            wait_ready(
                request,
                "identity.localhost",
                "/realms/platform/.well-known/openid-configuration",
            )
            wait_ready(request, "api-provider.apps.localhost", "/api/identity")
            for host, path, expected in (
                (
                    "identity.localhost",
                    "/realms/platform/.well-known/openid-configuration",
                    200,
                ),
                (
                    "identity.localhost",
                    "/realms/platform/protocol/openid-connect/certs",
                    200,
                ),
                ("api-provider.apps.localhost", "/api/identity", 200),
                ("identity.localhost", "/admin/", 404),
                (
                    "identity.localhost",
                    "/realms/master/protocol/openid-connect/token",
                    404,
                ),
                ("identity.localhost", "/realms/platform/account", 404),
                ("console-20000.apps.localhost", "/", 404),
            ):
                assert request(host, path) == expected, "Gateway route mismatch"
            assert (
                request("api-provider.apps.localhost", "/", "platform.localhost") == 421
            ), "Mismatched SNI/Host accepted"
            try:
                request("platform.localhost", "/projects")
            except ssl.SSLError:
                pass
            else:
                raise AssertionError("Operator hostname unexpectedly has a TLS route")
            print(
                "PASS verified local TLS; application and issuer routes; admin/master/account/console denial; SNI/Host confinement"
            )
    finally:
        command("rm", "-f", "-v", gateway, backend, check=False)
        command("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
