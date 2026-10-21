"""Edge routing, required negative authorization, and scoped audit assertions."""

import http.client
import json
import socket
import ssl
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from ..harness import require, wait_for


def check_edge(fixture, config, smoke):
    host = fixture.project + "." + config["APPS_DOMAIN"]
    # This suite tests lifecycle without a named store binding. The fixture's
    # readiness endpoint requires PostgreSQL; its identity endpoint proves HTTP
    # routing without restoring the removed implicit database access.
    path = "/" if smoke else "/api/identity"

    def ready():
        connection = None
        try:
            if host.endswith(".localhost"):
                connection = http.client.HTTPConnection("127.0.0.1", 80, timeout=10)
            else:
                connection = http.client.HTTPSConnection(host, 443, timeout=10)
                connection.sock = ssl.create_default_context().wrap_socket(
                    socket.create_connection(("127.0.0.1", 443), timeout=10),
                    server_hostname=host,
                )
            connection.request("GET", path, headers={"Host": host})
            return connection.getresponse().status == 200
        except OSError:
            return False
        finally:
            if connection:
                connection.close()

    wait_for(ready, "edge_routing_timeout")
    response = fixture.api.http.get(fixture.api.url + "/projects")
    require(response.status_code in (401, 403), "unauthenticated_project_access")
    fixture.check("authentication-and-edge-routing")


def check_access_and_audit(fixture, other, secret_values):
    before = fixture.request("GET", "/secrets")["secrets"]
    calls = [
        ("GET", "/configuration", None),
        ("PUT", "/configuration", {"values": {"DENIED": "1"}}),
        ("GET", "/secrets", None),
        ("PUT", "/secrets/DENIED_SECRET", {"value": "synthetic"}),
        ("POST", "/secrets/DENIED_SECRET/confirm", None),
        ("POST", "/secrets/DENIED_SECRET/revert", None),
        ("DELETE", "/secrets/DENIED_SECRET", None),
        ("GET", "/logs", None),
        ("GET", "/resource-usage", None),
        ("GET", "/revisions", None),
        ("GET", "/retirement-preview", None),
        ("POST", "/restart", None),
    ]
    for method, suffix, body in calls:
        other.request(method, fixture.path + suffix, body, statuses=(403, 404))
    for suffix in ("/configuration", "/secrets", "/logs"):
        response = fixture.api.http.get(fixture.api.url + fixture.path + suffix)
        require(response.status_code == 401, "unauthenticated_read_allowed")
    require(
        fixture.request("GET", "/secrets")["secrets"] == before,
        "denied_request_changed_secrets",
    )
    fixture.check("ungranted-user-and-unauthenticated-denial")
    for suffix in ("/configuration", "/logs", "/resource-usage"):
        fixture.request("GET", suffix)
    query = urlencode(
        {
            "start": fixture.report["startedAt"],
            "end": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            "limit": 10000,
        }
    )
    payload = fixture.api.request("GET", "/operator/audit/events?" + query)
    text = json.dumps(payload)
    require(
        all(value not in text for value in secret_values),
        "secret_value_in_audit_export",
    )
    events = [
        event
        for event in payload["events"]
        if event.get("target_id") == fixture.project
    ]
    seen = {(event["action"], event["result"]) for event in events}
    for action in (
        "project.secret.set",
        "project.secret.delete",
        "project.configuration.read",
        "project.logs.read",
        "project.usage.inspect",
    ):
        require(
            (action, "succeeded") in seen, "missing_audit_" + action.replace(".", "_")
        )
    require(
        any(
            "LIFECYCLE_SECRET" in json.dumps(event["detail"])
            for event in events
            if event["action"] == "project.secret.set"
        ),
        "secret_name_missing_from_audit",
    )
    fixture.check("required-audit-actions-secret-name-and-value-redaction")
