"""Issuance shared by the human-authorized API and trusted host bootstrap.

Host bootstrap is an operator command inside the API container, not an HTTP
endpoint or an authentication bypass exposed to test credentials.
"""

import json
import sys

from fastapi import HTTPException

from .audit import Actor
from .identity import Principal


def issue_test_runner(control, body, created_by, actor):
    """Create a bounded credential and record its actual authorizing actor."""
    provider = None
    try:
        provider = control.create_credential_client(
            "Platform test runner: " + body.name
        )
        machine = Principal(
            control.verifier.issuer, provider["subject"], "Test runner " + body.name
        )
        with control.connect() as conn, conn.transaction():
            control.grant_role(conn, machine, "platform", None, "platform-admin")
            row = conn.execute(
                """INSERT INTO deployment_credentials(
                    name, kind, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at)
                VALUES (%s,'test-runner',NULL,%s,%s,%s,%s,'active',%s,%s,
                        now()+make_interval(days => %s))
                RETURNING credential_id, name, kind, project, environment, status, created_at,
                          expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id""",
                (
                    body.name,
                    machine.issuer,
                    machine.subject,
                    provider["client_id"],
                    provider["provider_resource_id"],
                    created_by.issuer,
                    created_by.subject,
                    body.expires_in_days,
                ),
            ).fetchone()
        result = {
            **control.public_credential_record(row),
            "token_endpoint": control.verifier.issuer
            + "/protocol/openid-connect/token",
            "client_id": provider["client_id"],
            "client_secret": provider["client_secret"],
        }
    except Exception as exc:
        if provider:
            try:
                control.delete_credential_client(provider["provider_resource_id"])
            except Exception:
                pass
        control.required_audit(
            actor,
            "test-runner-credential.create",
            "platform",
            None,
            "failed",
            {"scope": "platform"},
            {"error_type": type(exc).__name__},
        )
        raise HTTPException(
            503, "Test-runner creation failed without returning a usable secret"
        )
    control.required_audit(
        actor,
        "test-runner-credential.create",
        "automation-credential",
        result["credential_id"],
        "succeeded",
        {"scope": "platform"},
        {"name": body.name, "expires_at": result["expires_at"]},
    )
    return result


def main():
    """Accept non-secret issuance options on stdin; emit the one-time secret."""
    from . import main as control
    from .api_models import TestRunnerCredentialCreate

    body = TestRunnerCredentialCreate.model_validate(json.load(sys.stdin))
    control.verifier = control.configured_verifier()
    created_by = Principal(control.verifier.issuer, "host-test-runner-bootstrap")
    result = issue_test_runner(
        control, body, created_by, Actor("system", "host-test-runner-bootstrap")
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
