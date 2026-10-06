"""The devplat executable."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Annotated

import typer

from .client import OperationFailed, OperationTimeout, PlatformClient, wait_for_operation
from .config import ConfigurationError, authentication_source, runtime_config
from .errors import ApiError
from .models import OperationStatus, application_body


app = typer.Typer(no_args_is_help=True, add_completion=False, help="Developer Platform command-line client.")
deploy_app = typer.Typer(no_args_is_help=True, help="Deploy versioned application specifications.")
auth_app = typer.Typer(no_args_is_help=True, help="Inspect the active non-persistent authentication source.")
app.add_typer(deploy_app, name="deploy")
app.add_typer(auth_app, name="auth")


def _read_json(path: str) -> dict[str, object]:
    try:
        contents = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return application_body(json.loads(contents))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise typer.BadParameter(f"unable to read a JSON application specification: {error}", param_hint="--file") from error


def _emit(value: object, output: str) -> None:
    if output == "json":
        typer.echo(json.dumps(value, separators=(",", ":"), default=str))
        return
    if isinstance(value, dict) and "operation_id" in value:
        typer.echo(f"Operation {value['operation_id']} is {value.get('state', 'unknown')} (revision {value.get('revision', 'unknown')}).")
        return
    typer.echo(str(value))


def _failure(error: Exception, output: str) -> typer.Exit:
    if isinstance(error, ApiError):
        payload = {"status": error.status_code, "detail": error.detail, "code": error.code, "request_id": error.request_id}
        if output == "json":
            typer.echo(json.dumps(payload, separators=(",", ":")), err=True)
        else:
            typer.echo(error.detail, err=True)
        return typer.Exit(error.exit_code)
    if isinstance(error, ConfigurationError):
        typer.echo(str(error), err=True)
        return typer.Exit(2)
    if isinstance(error, OperationFailed):
        typer.echo(f"Operation {error.status.operation_id} failed: {error}", err=True)
        return typer.Exit(9)
    if isinstance(error, OperationTimeout):
        typer.echo(f"{error} Resume with devplat operations watch {error.operation_id} when available.", err=True)
        return typer.Exit(10)
    typer.echo(str(error), err=True)
    return typer.Exit(8)


@auth_app.command("status")
def auth_status(
    output: Annotated[str, typer.Option("--output", case_sensitive=False)] = "table",
) -> None:
    """Show the active authentication source without disclosing credentials."""
    try:
        source = authentication_source(runtime_config())
        _emit({"source": source, "persistent": False}, output)
    except Exception as error:
        raise _failure(error, output) from None


@deploy_app.command("apply")
def deploy_apply(
    project: Annotated[str, typer.Option("--project", min=1, help="Target project name.")],
    file: Annotated[str, typer.Option("--file", help="JSON specification file, or - for stdin.")],
    wait: Annotated[bool, typer.Option("--wait", help="Wait for durable operation success and readiness.")] = False,
    timeout: Annotated[float, typer.Option("--timeout", min=1.0, help="Maximum wait time in seconds.")] = 300.0,
    poll_interval: Annotated[float, typer.Option("--poll-interval", min=0.1, help="Operation poll interval in seconds.")] = 2.0,
    if_match: Annotated[str | None, typer.Option("--if-match", help="Expected current revision.")] = None,
    output: Annotated[str, typer.Option("--output", case_sensitive=False)] = "table",
) -> None:
    """Apply one JSON application specification using environment authentication."""
    if output not in {"table", "json", "plain"}:
        raise typer.BadParameter("must be table, json, or plain", param_hint="--output")
    try:
        body = _read_json(file)
        config = runtime_config()
        client = PlatformClient(config)
        try:
            token = client.access_token()
            accepted = client.deploy(project, body, token, if_match)
            if not wait:
                _emit(accepted.model_dump(), output)
                return

            def update(status: OperationStatus) -> None:
                if output != "json":
                    typer.echo(
                        f"Operation {status.operation_id}: {status.state}; readiness {status.readiness.state}.",
                        err=True,
                    )

            completed = wait_for_operation(
                client, accepted, token, timeout, poll_interval, time.monotonic, time.sleep, update
            )
            _emit(completed.model_dump(), output)
        finally:
            client.close()
    except typer.BadParameter:
        raise
    except KeyboardInterrupt:
        typer.echo("Waiting interrupted; the durable platform operation continues.", err=True)
        raise typer.Exit(10) from None
    except Exception as error:
        raise _failure(error, output) from None


def main() -> None:
    app()


if __name__ == "__main__":
    main()
