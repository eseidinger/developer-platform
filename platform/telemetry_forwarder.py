"""Pod-local OTLP HTTP bridge with a freshly read projected token per batch."""

import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 262144
TOKEN_FILE = "/var/run/platform-telemetry/token"
GATEWAY = os.environ.get("TELEMETRY_GATEWAY_URL", "http://172.30.80.13:4318/v1/traces")
_slots = threading.BoundedSemaphore(4)
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _reply(self, status, body=b""):
        self.send_response(status)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if (
            self.path != "/v1/traces"
            or self.headers.get("Content-Type", "").split(";", 1)[0]
            != "application/x-protobuf"
            or self.headers.get("Transfer-Encoding")
        ):
            self._reply(415)
            return
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._reply(411)
            return
        if not 0 < size <= MAX_BODY:
            self._reply(413)
            return
        if not _slots.acquire(blocking=False):
            self._reply(429)
            return
        try:
            body = self.rfile.read(size)
            if len(body) != size:
                self._reply(400)
                return
            with open(TOKEN_FILE, "rb") as source:
                token = source.read(8193).strip()
            if not 0 < len(token) <= 8192 or any(byte in token for byte in b"\r\n\t "):
                self._reply(503)
                return
            request = urllib.request.Request(
                GATEWAY,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/x-protobuf",
                    "Authorization": "Bearer " + token.decode("ascii"),
                },
            )
            with _opener.open(request, timeout=2) as response:
                result = response.read(4096)
            self._reply(200, result)
        except (OSError, UnicodeError, urllib.error.URLError, ValueError):
            self._reply(503)
        finally:
            _slots.release()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 4318), Handler).serve_forever()
