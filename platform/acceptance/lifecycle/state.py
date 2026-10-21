"""Configuration revisions and write-only secret adoption on the owned fixture."""

import base64
import json
from uuid import uuid4

from ..harness import require
from ..human_database import wait_deployment


def check_configuration(fixture):
    original = fixture.request("GET", "/configuration")
    for values in ({"PGHOST": "x"}, {"DB_PASSWORD": "x"}, {"A": "x" * 2000}):
        result = fixture.request(
            "PUT", "/configuration", {"values": values}, statuses=(422,)
        )
        require(
            result["code"] == "invalid_configuration", "invalid_configuration_accepted"
        )
    fixture.request(
        "PUT",
        "/configuration",
        {"values": {}},
        etag=original["revision"] + 5,
        statuses=(409,),
    )
    previous = original["revision"]
    # Exercise full replacement, including clear, only on our disposable project.
    for values in (
        {"DRILL_MODE": "one", "DRILL_FLAG": "on"},
        {"DRILL_MODE": "two"},
        {},
        original["values"],
    ):
        accepted = fixture.request(
            "PUT", "/configuration", {"values": values}, etag=previous, statuses=(202,)
        )
        wait_deployment(fixture.api, accepted)
        fixture.activate("configuration")
        observed = fixture.request("GET", "/configuration")
        require(
            observed["values"] == values and observed["revision"] > previous,
            "configuration_revision_mismatch",
        )
        previous = observed["revision"]
    require(
        fixture.request("GET", "/drift")["state"] == "in_sync", "configuration_drift"
    )
    fixture.check("configuration-validation-concurrency-replacement-and-drift")


def check_secrets(fixture):
    name = "LIFECYCLE_SECRET"
    first, second = "fixture-" + uuid4().hex, "rotated-" + uuid4().hex
    seen = []

    def call(method, suffix="", body=None, statuses=(200,)):
        result = fixture.request(method, "/secrets" + suffix, body, statuses=statuses)
        seen.append(json.dumps(result))
        return result

    def stored(secret):
        value = fixture.kubectl(
            "get", "secret", secret, "-o", "jsonpath={.data." + name + "}"
        ).stdout
        return base64.b64decode(value).decode()

    def put(value):
        before = fixture.pods()
        call("PUT", "/" + name, {"value": value}, statuses=(202,))
        fixture.activate("secrets")
        after = fixture.pods()
        require(after and before != after, "secret_rollout_missing")

    call("PUT", "/PGHOST", {"value": first}, statuses=(422,))
    put(first)
    require(stored("app-secrets") == first, "secret_not_stored")
    listing = call("GET")["secrets"]
    require(
        len(listing) == 1 and listing[0]["version"] == 1, "unexpected_secret_listing"
    )
    # The neutral fixture is Python-based, so adoption is verified directly rather
    # than silently skipped when a sample image lacks printenv.
    adopted = fixture.kubectl(
        "exec",
        "deployment/" + fixture.project,
        "--",
        "python",
        "-c",
        "import os; print(os.environ['LIFECYCLE_SECRET'])",
    ).stdout.strip()
    require(adopted == first, "secret_not_adopted")
    put(second)
    listing = call("GET")["secrets"][0]
    require(
        (listing["version"], listing["state"]) == (2, "rotating"),
        "secret_rotation_state",
    )
    require(stored("app-secrets-previous") == first, "previous_secret_missing")
    deployment = fixture.kubectl(
        "get", "deployment", fixture.project, "-o", "json"
    ).stdout
    require("app-secrets-previous" not in deployment, "previous_secret_mounted")
    call("POST", "/" + name + "/revert", statuses=(202,))
    fixture.activate("secrets")
    require(
        stored("app-secrets") == first and call("GET")["secrets"][0]["version"] == 3,
        "secret_revert_failed",
    )
    put(second)
    require(
        call("POST", "/" + name + "/confirm")["state"] == "active",
        "secret_confirm_failed",
    )
    require(
        fixture.kubectl(
            "get", "secret", "app-secrets-previous", "-o", "jsonpath={.data}"
        ).stdout
        in ("", "{}"),
        "previous_secret_not_revoked",
    )
    call("POST", "/" + name + "/confirm", statuses=(409,))
    for suffix in ("/revisions", "/configuration", "/drift"):
        seen.append(json.dumps(fixture.request("GET", suffix)))
    call("DELETE", "/" + name, statuses=(202,))
    fixture.activate("secrets")
    require(call("GET")["secrets"] == [], "secret_delete_failed")
    call("DELETE", "/" + name, statuses=(404,))
    logs = fixture.command(
        [
            "docker",
            "compose",
            "logs",
            "--no-color",
            "--since",
            fixture.report["startedAt"],
            "platform-api",
        ]
    ).stdout
    require(
        all(
            value not in response
            for value in (first, second)
            for response in [*seen, logs]
        ),
        "secret_value_disclosed",
    )
    fixture.check("secret-adoption-rotation-revert-confirm-and-redaction")
    return first, second
