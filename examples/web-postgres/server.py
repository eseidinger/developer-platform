"""Small web/PostgreSQL example. The platform, not this app, handles ingress auth."""
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg


def visit_count() -> int:
    with psycopg.connect(connect_timeout=5) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS demo_visits (id integer PRIMARY KEY, count bigint NOT NULL)")
        return conn.execute("""INSERT INTO demo_visits VALUES (1, 1)
            ON CONFLICT (id) DO UPDATE SET count=demo_visits.count+1 RETURNING count""").fetchone()[0]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Never log URLs, forwarded identity headers, cookies, or credentials.
        pass

    def reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        print(json.dumps({"event": "demo.request", "status": status}), flush=True)

    def do_GET(self):
        if self.path == "/health/ready":
            if os.environ.get("DEMO_FAIL_READY") == "true":
                return self.reply(503, b"not ready", "text/plain")
            try:
                with psycopg.connect(connect_timeout=5) as conn:
                    conn.execute("SELECT 1")
            except psycopg.Error:
                return self.reply(503, b"database unavailable", "text/plain")
            return self.reply(200, b"ready", "text/plain")
        if self.path == "/api/visits":
            try:
                count = visit_count()
            except psycopg.Error:
                return self.reply(503, b'{"error":"database unavailable"}', "application/json")
            return self.reply(200, json.dumps({"visits": count}).encode(), "application/json")
        if self.path == "/":
            identity = html.escape(self.headers.get("X-Platform-Principal-Name", "visitor"), quote=True)
            page = ("<!doctype html><title>Developer Platform sample</title>"
                    "<h1>Web + PostgreSQL</h1><p>Hello, " + identity + ".</p>"
                    "<p><a href='/api/visits'>Increment the shared visit counter</a></p>")
            return self.reply(200, page.encode(), "text/html; charset=utf-8")
        return self.reply(404, b"not found", "text/plain")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
