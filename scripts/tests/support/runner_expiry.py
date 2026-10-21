"""Two-stage credential expiry proof using a still-unexpired, previously valid JWT."""

import base64
import hashlib
import json
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ExpiryError(Exception):
    """An actionable fixed code, safe to print without response details."""


def require(condition, code):
    if not condition:
        raise ExpiryError(code)


def request(url, *, form=None, token=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    body = urlencode(form).encode() if form else None
    try:
        with urlopen(Request(url, data=body, headers=headers), timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def verify(payload, *, call=request, now=time.time, sleep=time.sleep):
    phase = payload["phase"]
    require(phase in ("active", "expired"), "invalid_phase")
    expiry = datetime.fromisoformat(payload["expires_at"])
    require(expiry.tzinfo is not None, "expiry_timezone_required")
    expiry = expiry.timestamp()
    path = Path(payload["state_file"])
    require(
        not path.parent.is_symlink()
        and path.parent.is_dir()
        and stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0,
        "private_evidence_parent_required",
    )
    identity = {
        key: payload[key]
        for key in ("api", "token_url", "client_id", "credential_id", "expires_at")
    }
    identity["secret_sha256"] = hashlib.sha256(
        payload["client_secret"].encode()
    ).hexdigest()
    form = {
        "grant_type": "client_credentials",
        "client_id": payload["client_id"],
        "client_secret": payload["client_secret"],
    }
    if phase == "active":
        require(now() < expiry, "credential_already_expired")
        require(not path.exists() and not path.is_symlink(), "evidence_file_exists")
        status, token = call(payload["token_url"], form=form)
        require(status == 200, "active_token_exchange_failed")
        bearer = token["access_token"]
        # The token came directly from the configured issuer. Decode only to
        # schedule the boundary; acceptance still requires real API requests.
        claims = json.loads(base64.urlsafe_b64decode(bearer.split(".")[1] + "==="))
        require(
            expiry < claims["exp"],
            "run_active_near_expiry_so_held_jwt_outlives_credential",
        )
        require(
            call(payload["api"].rstrip("/") + "/projects", token=bearer)[0] == 200,
            "active_api_access_failed",
        )
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(
                {**identity, "access_token": bearer, "token_expires_at": claims["exp"]},
                output,
            )
    else:
        require(now() >= expiry, "credential_not_yet_expired")
        require(
            path.is_file()
            and not path.is_symlink()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
            "private_evidence_file_required",
        )
        evidence = json.loads(path.read_text())
        require(
            all(evidence.get(key) == value for key, value in identity.items()),
            "evidence_identity_mismatch",
        )
        require(
            now() < evidence["token_expires_at"],
            "held_jwt_already_expired_repeat_boundary_drill",
        )
        # Provider-client removal is asynchronous. Bound retries by the held
        # JWT's lifetime so token expiry can never stand in for grant enforcement.
        status, body = call(payload["token_url"], form=form)
        while status == 200 and now() < evidence["token_expires_at"] - 5:
            sleep(2)
            status, body = call(payload["token_url"], form=form)
        require(
            status in (400, 401)
            and body.get("error") in ("invalid_client", "unauthorized_client"),
            "expired_credential_not_rejected",
        )
        require(
            call(
                payload["api"].rstrip("/") + "/projects", token=evidence["access_token"]
            )[0]
            == 403,
            "held_unexpired_jwt_not_denied",
        )
        require(
            now() < evidence["token_expires_at"], "held_jwt_expired_during_verification"
        )
    return {"phase": phase, "result": "passed", "heldTokenOutlivesCredential": True}


def main():
    try:
        print(json.dumps(verify(json.load(sys.stdin))))
        return 0
    except (ExpiryError, OSError, ValueError, KeyError, IndexError) as error:
        print(
            json.dumps(
                {
                    "result": "failed",
                    "code": str(error)
                    if isinstance(error, ExpiryError)
                    else "expiry_dependency_failure",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
