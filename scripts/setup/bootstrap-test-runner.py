#!/usr/bin/env python3
"""Issue a private, expiring test credential through trusted local Docker access."""

import argparse
import json
import os
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def bootstrap(args):
    """Reserve the destination before creating a one-time provider secret."""
    origin = urlsplit(args.api)
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
        or (
            origin.scheme == "http"
            and origin.hostname not in {"localhost", "127.0.0.1", "::1"}
        )
        or args.confirm_environment != args.api
    ):
        raise ValueError("Confirm a valid platform API origin explicitly")
    path = args.output.absolute()
    if path.parent.is_symlink():
        raise ValueError("Credential directory must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise ValueError("Credential directory must have private permissions")
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "platform-api",
                    "python",
                    "-m",
                    "app.automation_credentials",
                ],
                cwd=ROOT,
                input=json.dumps(
                    {"name": args.name, "expires_in_days": args.expires_in_days}
                ),
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            if result.returncode:
                raise RuntimeError(
                    "Host bootstrap failed; inspect private API diagnostics"
                )
            value = json.loads(result.stdout)
            payload = {
                "platform_api_url": args.api.rstrip("/"),
                "platform_oidc_token_url": value["token_endpoint"],
                "platform_test_runner_client_id": value["client_id"],
                "platform_test_runner_client_secret": value["client_secret"],
                "platform_test_runner_credential_id": value["credential_id"],
                "platform_test_runner_expires_at": value["expires_at"],
            }
            json.dump(payload, output, indent=2)
            output.write("\n")
        return payload["platform_test_runner_credential_id"]
    except BaseException:
        # Remove only the file this process reserved; never overwrite an old secret.
        path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="local-functional-tests")
    parser.add_argument("--expires-in-days", type=int, choices=range(1, 31), default=1)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--confirm-environment", required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".runtime/test-runner.json"
    )
    args = parser.parse_args()
    try:
        identifier = bootstrap(args)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        parser.exit(
            1,
            "Test-runner bootstrap failed; no secret was printed. Check configuration, private output permissions, and API availability.\n",
        )
    print(
        f"Created expiring test runner {identifier}; credential saved to {args.output}"
    )


if __name__ == "__main__":
    main()
