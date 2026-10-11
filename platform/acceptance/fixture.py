"""Deliberately authorization-free neutral fixture; NEVER use for real application data.

The platform alone controls access. This fixture reports only received identity
context and synthetic state, and never exposes credentials or token values.
"""
import argparse
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import psycopg


VERSION = 1
HEADERS = ("Id", "Kind", "Issuer", "Subject", "Group-Ids", "Client-Id", "Name", "Email")


def identity(headers):
    return {"principal": {k: headers.get("X-Platform-Principal-" + k) for k in HEADERS},
            "correlationHash": hashlib.sha256(headers.get("X-Correlation-Id", "").encode()).hexdigest(),
            "authorizationPresent": "Authorization" in headers,
            "platformCookiePresent": "__Host-platform-" in headers.get("Cookie", "")}


def state(value=None):
    with psycopg.connect(connect_timeout=5) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS acceptance_state (id integer PRIMARY KEY, marker text NOT NULL)")
        initial = os.environ["FIXTURE_ROLE"] + "-" + os.environ["ACCEPTANCE_RUN_ID"]
        conn.execute("INSERT INTO acceptance_state VALUES (1,%s) ON CONFLICT DO NOTHING", (initial,))
        if value is not None:
            conn.execute("UPDATE acceptance_state SET marker=%s WHERE id=1", (value,))
        return conn.execute("SELECT marker FROM acceptance_state WHERE id=1").fetchone()[0]


def probe(correlation=None):
    if correlation not in (None, os.environ["ACCEPTANCE_RUN_ID"]):
        raise ValueError("Only the synthetic run correlation is supported")
    prefixes = [k.removesuffix("_CLIENT_ID") for k in os.environ
                if k.startswith("ACCESS_") and k.endswith("_CLIENT_ID")]
    if len(prefixes) != 1:
        raise ValueError("Exactly one managed service binding is required")
    prefix = prefixes[0]
    target = os.environ["PROVIDER_URL"]
    endpoint = os.environ[prefix + "_TOKEN_URL"]
    if any(urlsplit(u).scheme != "https" for u in (target, endpoint)):
        raise ValueError("Public HTTPS is required")
    with urlopen(Request(endpoint, data=urlencode({"grant_type": "client_credentials",
            "client_id": os.environ[prefix + "_CLIENT_ID"],
            "client_secret": os.environ[prefix + "_CLIENT_SECRET"]}).encode()), timeout=10) as response:
        token = json.load(response)["access_token"]
    # TLS verification is mandatory. The target is fixed configuration, not caller input.
    with urlopen(Request(target + "/api/identity", headers={"Authorization": "Bearer " + token,
            **({"X-Correlation-Id": correlation} if correlation else {})}), timeout=10) as response:
        return {"providerStatus": response.status, "provider": json.load(response)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No request headers, OAuth tokens, query strings, or identity values in logs.

    def reply(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def dispatch(self):
        path = urlsplit(self.path).path
        try:
            if path == "/health/ready":
                state()
                body = {"ready": True}
            elif path.endswith("/identity"):
                body = identity(self.headers)
            elif path == "/api/state":
                value = None
                if self.command == "POST":
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 256:
                        return self.reply(400, {"code": "invalid_marker"})
                    value = json.loads(self.rfile.read(size))["marker"]
                    if not isinstance(value, str) or not 1 <= len(value) <= 100:
                        return self.reply(400, {"code": "invalid_marker"})
                body = {"marker": state(value)}
            elif path == "/api/probe":
                body = probe(self.headers.get("X-Correlation-Id"))
            else:
                return self.reply(404, {"code": "fixture_route_missing"})
            self.reply(200, {"fixtureVersion": VERSION, "runId": os.environ["ACCEPTANCE_RUN_ID"], **body})
        except (HTTPError, OSError, psycopg.Error, ValueError, KeyError):
            self.reply(503, {"code": "fixture_dependency_unavailable"})

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_OPTIONS = dispatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help="Private service using the same readiness/state contract")
    parser.parse_args()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
