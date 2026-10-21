"""The devplat executable."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated

import typer

from .client import PlatformClient, wait_for_operation
from .commands import context_state as _state
from .commands import emit, fail, register, watch_access
from .config import ConfigurationError, authentication_source, runtime_config
from .errors import ApiError
from .models import OperationAccepted, OperationStatus, application_body
from .profiles import Profile, ProfileStore, SessionStore
from .registry import COMMANDS
from .tunnel import run_tunnel, ssh_command

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Developer Platform command-line client.",
)
deploy_app = typer.Typer(
    no_args_is_help=True, help="Deploy versioned application specifications."
)
auth_app = typer.Typer(
    no_args_is_help=True, help="Inspect, create, or clear human login sessions."
)
app.add_typer(deploy_app, name="deploy")
app.add_typer(auth_app, name="auth")


def _version_callback(value: bool):
    if value:
        from importlib.metadata import version

        typer.echo(version("developer-platform-cli"))
        raise typer.Exit()


@dataclass(frozen=True)
class Settings:
    profile: str | None = None
    api_url: str | None = None
    output: str | None = None
    insecure: bool = False
    quiet: bool = False
    debug: bool = False


@app.callback()
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed CLI version.",
        ),
    ] = False,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    api_url: Annotated[str | None, typer.Option("--api-url")] = None,
    output: Annotated[str | None, typer.Option("--output")] = None,
    no_color: Annotated[bool, typer.Option("--no-color")] = False,
    quiet: Annotated[bool, typer.Option("--quiet")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    insecure: Annotated[bool, typer.Option("--insecure")] = False,
):
    if output and output not in {"table", "plain", "json"}:
        raise typer.BadParameter("Use table, plain, or json.", param_hint="--output")
    if no_color:
        import os

        os.environ["NO_COLOR"] = "1"
    if insecure:
        typer.echo("TLS verification disabled for this invocation.", err=True)
    ctx.obj = Settings(profile, api_url, output, insecure, quiet, debug)


def _effective_output(ctx: typer.Context, output: str | None) -> str:
    if output or _state(ctx).output:
        return output or _state(ctx).output
    if (
        not _state(ctx).profile
        and os.environ.get("PLATFORM_API_URL")
        and any(
            os.environ.get(key)
            for key in (
                "PLATFORM_ACCESS_TOKEN",
                "PLATFORM_TOKEN_ENDPOINT",
                "PLATFORM_CLIENT_ID",
                "PLATFORM_CLIENT_SECRET",
            )
        )
    ):
        return "table"
    _, selected = ProfileStore().selected(_state(ctx).profile)
    return selected.output if selected else "table"


def _read_json(path: str) -> dict[str, object]:
    try:
        contents = (
            sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        )
        return application_body(json.loads(contents))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise typer.BadParameter(
            f"unable to read a JSON application specification: {error}",
            param_hint="--file",
        ) from error


def _emit(value: object, output: str) -> None:
    if output == "json":
        typer.echo(json.dumps(value, separators=(",", ":"), default=str))
        return
    if isinstance(value, dict) and "operation_id" in value:
        typer.echo(
            f"Operation {value['operation_id']} is {value.get('state', 'unknown')} (revision {value.get('revision', 'unknown')})."
        )
        return
    typer.echo(str(value))


@auth_app.command("status")
def auth_status(
    ctx: typer.Context,
    output: Annotated[
        str | None, typer.Option("--output", case_sensitive=False)
    ] = None,
) -> None:
    """Show the active authentication source without disclosing credentials."""
    try:
        config = runtime_config(
            profile_name=_state(ctx).profile,
            api_url_override=_state(ctx).api_url,
            insecure=_state(ctx).insecure,
        )
        source = authentication_source(config)
        result = {"source": source, "persistent": False}
        if source == "human-profile-session":
            session = SessionStore(config.profile_name, config.profile).get()
            result = {
                "source": source,
                "persistent": bool(session),
                "profile": config.profile_name,
                "subject": session["subject"] if session else None,
            }
        _emit(result, _effective_output(ctx, output))
    except Exception as error:
        raise fail(error, output or _state(ctx).output or "table") from None


@deploy_app.command("apply")
def deploy_apply(
    ctx: typer.Context,
    project: Annotated[
        str, typer.Option("--project", min=1, help="Target project name.")
    ],
    file: Annotated[
        str, typer.Option("--file", help="JSON specification file, or - for stdin.")
    ],
    wait: Annotated[
        bool,
        typer.Option(
            "--wait", help="Wait for durable operation success and readiness."
        ),
    ] = False,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1.0, help="Maximum wait time in seconds.")
    ] = 300.0,
    poll_interval: Annotated[
        float,
        typer.Option(
            "--poll-interval", min=0.1, help="Operation poll interval in seconds."
        ),
    ] = 2.0,
    if_match: Annotated[
        str | None, typer.Option("--if-match", help="Expected current revision.")
    ] = None,
    output: Annotated[
        str | None, typer.Option("--output", case_sensitive=False)
    ] = None,
) -> None:
    """Apply one JSON application specification using environment authentication."""
    output = _effective_output(ctx, output)
    if output not in {"table", "json", "plain"}:
        raise typer.BadParameter("must be table, json, or plain", param_hint="--output")
    try:
        body = _read_json(file)
        config = runtime_config(
            profile_name=_state(ctx).profile,
            api_url_override=_state(ctx).api_url,
            insecure=_state(ctx).insecure,
        )
        client = PlatformClient(config)
        client.debug = _state(ctx).debug
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
                client,
                accepted,
                token,
                timeout,
                poll_interval,
                time.monotonic,
                time.sleep,
                update,
            )
            _emit(completed.model_dump(), output)
        finally:
            client.close()
    except typer.BadParameter:
        raise
    except KeyboardInterrupt:
        typer.echo(
            "Waiting interrupted; the durable platform operation continues.", err=True
        )
        raise typer.Exit(10) from None
    except Exception as error:
        raise fail(error, output) from None


profiles_app = typer.Typer(
    no_args_is_help=True, help="Named non-secret connection profiles."
)
app.add_typer(profiles_app, name="profiles")


@profiles_app.command("create")
def profile_create(
    name: str,
    api_url: Annotated[str, typer.Option("--api-url")],
    issuer: Annotated[str, typer.Option("--issuer")],
    client_id: Annotated[str, typer.Option("--client-id")] = "platform-cli",
    ca_bundle: Annotated[str | None, typer.Option("--ca-bundle")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    output: Annotated[str, typer.Option("--output")] = "table",
):
    """Save only API and OIDC connection settings."""
    try:
        store = ProfileStore()
        store.create(
            name, Profile(api_url, issuer, client_id, ca_bundle, project, output)
        )
        emit({"profile": name, "active": store.read().get("active") == name}, output)
    except Exception as error:
        raise fail(error, output) from None


@profiles_app.command("show")
def profile_show(
    ctx: typer.Context,
    name: str | None = None,
    output: Annotated[str | None, typer.Option("--output")] = None,
):
    """Display a profile without credentials."""
    try:
        selected, profile = ProfileStore().selected(name or _state(ctx).profile)
        if profile is None:
            raise ConfigurationError("No profile selected.")
        emit({"name": selected, **asdict(profile)}, _effective_output(ctx, output))
    except Exception as error:
        raise fail(error, output or _state(ctx).output or "table") from None


@profiles_app.command("use")
def profile_use(name: str):
    """Select the default profile."""
    try:
        ProfileStore().use(name)
        emit({"active": name}, "table")
    except Exception as error:
        raise fail(error) from None


@profiles_app.command("delete")
def profile_delete(name: str):
    """Remove a profile and its bound keyring session."""
    try:
        _, profile = ProfileStore().selected(name)
        SessionStore(name, profile).delete()
        ProfileStore().delete(name)
        emit({"deleted": name}, "table")
    except Exception as error:
        raise fail(error) from None


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    timeout: Annotated[float, typer.Option("--timeout", min=1)] = 300,
    open_browser: Annotated[bool, typer.Option("--open-browser")] = False,
    output: Annotated[str | None, typer.Option("--output")] = None,
):
    """Sign in with OIDC Device Authorization and PKCE."""
    selected_output = _effective_output(ctx, output)
    try:
        client = PlatformClient(
            runtime_config(
                profile_name=_state(ctx).profile,
                api_url_override=_state(ctx).api_url,
                insecure=_state(ctx).insecure,
            )
        )
        try:

            def notify(uri: str, code: str):
                typer.echo("Open " + uri + " and enter code " + code, err=True)
                if open_browser:
                    import webbrowser

                    webbrowser.open(uri)

            subject = client.human_authentication().login(notify, timeout=timeout)
            emit(
                {"profile": client.config.profile_name, "subject": subject},
                selected_output,
            )
        finally:
            client.close()
    except KeyboardInterrupt:
        raise typer.Exit(10) from None
    except Exception as error:
        raise fail(error, selected_output) from None


@auth_app.command("logout")
def auth_logout(
    ctx: typer.Context, output: Annotated[str | None, typer.Option("--output")] = None
):
    """Clear the human session and request provider revocation."""
    selected_output = _effective_output(ctx, output)
    try:
        client = PlatformClient(
            runtime_config(
                profile_name=_state(ctx).profile,
                api_url_override=_state(ctx).api_url,
                insecure=_state(ctx).insecure,
            )
        )
        try:
            client.human_authentication().logout()
            emit(
                {"profile": client.config.profile_name, "logged_out": True},
                selected_output,
            )
        finally:
            client.close()
    except Exception as error:
        raise fail(error, selected_output) from None


def _tree(parent: typer.Typer, names: tuple[str, ...]) -> typer.Typer:
    for name in names:
        children = getattr(parent, "_devplat_children", None)
        if children is None:
            children = {}
            parent._devplat_children = children
        if name not in children:
            child = typer.Typer(
                no_args_is_help=True,
                help=name.replace("-", " ").capitalize() + " commands.",
            )
            parent.add_typer(child, name=name)
            children[name] = child
        parent = children[name]
    return parent


for specification in COMMANDS:
    if specification.command == "deploy apply":
        continue
    if specification.command == "logs":
        register(_tree(app, ("logs",)), specification)
        continue
    parts = specification.command.split()
    register(_tree(app, tuple(parts[:-1])), specification)


def _client(ctx: typer.Context) -> PlatformClient:
    client = PlatformClient(
        runtime_config(
            profile_name=_state(ctx).profile,
            api_url_override=_state(ctx).api_url,
            insecure=_state(ctx).insecure,
        )
    )
    client.debug = _state(ctx).debug
    return client


@_tree(app, ("stores", "access")).command("tunnel")
def stores_access_tunnel(
    ctx: typer.Context,
    credential_id: str,
    identity_file: Annotated[
        str,
        typer.Option(
            "--identity-file", help="Private Ed25519 key registered with the platform."
        ),
    ],
    known_hosts: Annotated[
        str, typer.Option("--known-hosts", help="Verified SSH host key file.")
    ],
    local_port: Annotated[int, typer.Option("--local-port", min=1, max=65535)],
):
    """Forward an active store lease to a local TCP port until interrupted."""
    try:
        from uuid import UUID

        credential_id = str(UUID(credential_id))
        client = _client(ctx)
        try:
            credential, _ = client.request_json(
                "GET", "/v1/store-access/credentials/" + credential_id
            )
        finally:
            client.close()
        command = ssh_command(credential, identity_file, known_hosts, local_port)
        typer.echo(
            f"{credential['provider']} tunnel on 127.0.0.1:{local_port}; press Ctrl-C to close.",
            err=True,
        )
        result = run_tunnel(command)
        if result:
            raise typer.Exit(result)
    except KeyboardInterrupt:
        raise typer.Exit(10) from None
    except typer.Exit:
        raise
    except Exception as error:
        raise fail(error) from None


@app.command("status")
def status(
    ctx: typer.Context,
    project: Annotated[str | None, typer.Option("--project")] = None,
    output: Annotated[str | None, typer.Option("--output")] = None,
):
    """Inspect project metadata and component state."""
    selected_output = _effective_output(ctx, output)
    try:
        client = _client(ctx)
        try:
            project = project or (
                client.config.profile.project if client.config.profile else None
            )
            if not project:
                raise ConfigurationError(
                    "Supply --project or select a profile with a default project."
                )
            projects, _ = client.request_json("GET", "/projects")
            row = next((item for item in projects if item.get("name") == project), None)
            if row is None:
                raise ApiError(404, "Project not found in authorized project list.")
            components, _ = client.request_json(
                "GET", "/projects/" + project + "/components"
            )
            emit({"project": row, "components": components}, selected_output)
        finally:
            client.close()
    except Exception as error:
        raise fail(error, selected_output) from None


@_tree(app, ("projects",)).command("show")
def projects_show(
    ctx: typer.Context,
    project: Annotated[str | None, typer.Option("--project")] = None,
    output: Annotated[str | None, typer.Option("--output")] = None,
):
    """Show an authorized project list entry."""
    selected_output = _effective_output(ctx, output)
    try:
        client = _client(ctx)
        try:
            project = project or (
                client.config.profile.project if client.config.profile else None
            )
            if not project:
                raise ConfigurationError(
                    "Supply --project or select a profile with a default project."
                )
            rows, _ = client.request_json("GET", "/projects")
            row = next((item for item in rows if item.get("name") == project), None)
            if row is None:
                raise ApiError(404, "Project not found in authorized project list.")
            emit(row, selected_output)
        finally:
            client.close()
    except Exception as error:
        raise fail(error, selected_output) from None


@_tree(app, ("operations",)).command("watch")
def operations_watch(
    ctx: typer.Context,
    operation_id: str,
    timeout: Annotated[float, typer.Option("--timeout", min=1)] = 300,
    poll_interval: Annotated[float, typer.Option("--poll-interval", min=0.1)] = 2,
    output: Annotated[str | None, typer.Option("--output")] = None,
):
    """Resume bounded deployment operation watching."""
    selected_output = _effective_output(ctx, output)
    try:
        client = _client(ctx)
        try:
            token = client.access_token()
            path = "/v1/operations/" + operation_id
            first = client.operation(path, token)
            accepted = OperationAccepted(
                operation_id=first.operation_id,
                state=first.state,
                revision=first.revision,
                status_url=path,
            )
            result = wait_for_operation(
                client,
                accepted,
                token,
                timeout,
                poll_interval,
                time.monotonic,
                time.sleep,
                lambda _: None,
            )
            emit(result.model_dump(), selected_output)
        finally:
            client.close()
    except Exception as error:
        raise fail(error, selected_output) from None


@_tree(app, ("access", "operations")).command("watch")
def access_operations_watch(
    ctx: typer.Context,
    operation_id: str,
    timeout: Annotated[float, typer.Option("--timeout", min=1)] = 300,
    poll_interval: Annotated[float, typer.Option("--poll-interval", min=0.1)] = 2,
    output: Annotated[str | None, typer.Option("--output")] = None,
):
    """Resume hosted access operation watching."""
    selected_output = _effective_output(ctx, output)
    try:
        client = _client(ctx)
        try:
            emit(
                watch_access(
                    client, operation_id, timeout, poll_interval, lambda _: None
                ),
                selected_output,
            )
        finally:
            client.close()
    except Exception as error:
        raise fail(error, selected_output) from None


@_tree(app, ("contract",)).command("check")
def contract_check(
    ctx: typer.Context, output: Annotated[str | None, typer.Option("--output")] = None
):
    """Report registry coverage of the packaged public API contract."""
    selected_output = _effective_output(ctx, output)
    from importlib.resources import files

    from .registry import EXCLUSIONS

    contract = json.loads(
        files("platform_cli").joinpath("api_contract.json").read_text()
    )
    expected = {
        (method.upper(), path)
        for path, methods in contract["paths"].items()
        for method in methods
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }
    actual = {(spec.method, spec.path) for spec in COMMANDS}
    missing = sorted(expected - actual - EXCLUSIONS.keys())
    extra = sorted(actual - expected)
    emit(
        {
            "covered": len(actual),
            "excluded": len(EXCLUSIONS),
            "missing": missing,
            "extra": extra,
        },
        selected_output,
    )
    if missing or extra:
        raise typer.Exit(7)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
