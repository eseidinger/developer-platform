"""Typer command construction and safe execution for the public API registry."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import typer

from .client import OperationFailed, OperationTimeout, PlatformClient, wait_for_operation
from .config import ConfigurationError, runtime_config
from .errors import ApiError
from .models import AccessOperation, AccessResource, OperationAccepted, OperationStatus
from .registry import COMMANDS, CommandSpec


SENSITIVE_KEYS = {"client_secret", "clientsecret", "access_token", "accesstoken", "refresh_token",
                  "refreshtoken", "id_token", "idtoken", "password", "private_key", "privatekey", "authorization"}


class AccessOperationFailed(RuntimeError):
    def __init__(self, operation_id: str, code: str | None):
        super().__init__("Access operation " + operation_id + " failed: " + (code or "unknown error") +
                         ". Inspect it and retry with the resource's current ETag.")
        self.operation_id = operation_id


def context_state(ctx: typer.Context):
    root = ctx.find_root()
    if root.obj is not None:
        return root.obj
    params = root.params
    return SimpleNamespace(profile=params.get("profile"), api_url=params.get("api_url"),
        output=params.get("output"), insecure=params.get("insecure", False),
        quiet=params.get("quiet", False), debug=params.get("debug", False))


def clean(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else clean(item, secrets)
                for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def emit(value: Any, output: str, *, one_time: bool = False) -> None:
    rendered = value if one_time else clean(value)
    if output == "json":
        typer.echo(json.dumps(rendered, separators=(",", ":"), default=str))
    elif output == "table" and isinstance(rendered, (dict, list)):
        rows = rendered.get("items", []) if isinstance(rendered, dict) else rendered
        if isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows):
            from rich.console import Console
            from rich.table import Table
            columns = [key for key in ("name", "project", "id", "kind", "role", "state", "status", "version")
                       if any(key in row for row in rows)]
            if columns:
                table = Table(show_header=True)
                for column in columns:
                    table.add_column(column)
                for row in rows:
                    table.add_row(*(str(row.get(column, "")) for column in columns))
                Console(file=sys.stdout, no_color=bool(os.environ.get("NO_COLOR"))).print(table)
                return
        typer.echo(json.dumps(rendered, indent=2, default=str))
    elif output == "plain" and isinstance(rendered, dict):
        typer.echo("\n".join(f"{key}={json.dumps(item, default=str)}" for key, item in rendered.items()))
    else:
        typer.echo(json.dumps(rendered, indent=2, default=str) if isinstance(rendered, (dict, list)) else str(rendered))


def fail(error: Exception, output: str = "table", secrets: tuple[str, ...] = ()) -> typer.Exit:
    if isinstance(error, ApiError):
        payload = {"status": error.status_code, "detail": error.detail, "code": error.code,
                   "request_id": error.request_id, "retryable": error.status_code in {429, 502, 503, 504}}
        typer.echo(json.dumps(clean(payload, secrets), separators=(",", ":")) if output == "json"
                   else clean(error.detail, secrets), err=True)
        return typer.Exit(error.exit_code)
    if isinstance(error, ConfigurationError):
        typer.echo(clean(str(error), secrets), err=True)
        return typer.Exit(2)
    if isinstance(error, (OperationFailed, AccessOperationFailed)):
        typer.echo(clean(str(error), secrets), err=True)
        return typer.Exit(9)
    if isinstance(error, OperationTimeout):
        typer.echo(clean(str(error), secrets), err=True)
        return typer.Exit(10)
    if isinstance(error, (ValueError, OSError, json.JSONDecodeError)):
        typer.echo("Invalid input or file; check the command arguments and JSON syntax.", err=True)
        return typer.Exit(2)
    typer.echo("The CLI could not complete the request; inspect the API or identity provider availability.", err=True)
    return typer.Exit(8)


def read_json(path: str) -> dict:
    try:
        if path == "-":
            raw = sys.stdin.read(8 * 1024 * 1024 + 1)
        else:
            selected = Path(path)
            if selected.stat().st_size > 8 * 1024 * 1024:
                raise ValueError()
            raw = selected.read_text(encoding="utf-8")
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError("Unable to read a JSON object from the selected file.") from None


def read_secret(path: str | None) -> str:
    if path is None:
        if not sys.stdin.isatty():
            raise ConfigurationError("Use --value-file PATH or - to provide a secret without a terminal.")
        import getpass
        return getpass.getpass("Secret value: ")
    if path == "-":
        return sys.stdin.readline(16385).removesuffix("\n")
    selected = Path(path)
    mode = selected.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ConfigurationError("Secret input file must be regular and readable only by its owner.")
    return selected.read_text(encoding="utf-8").removesuffix("\n")


def etag(value: str | None, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ConfigurationError("Supply the current quoted ETag with --if-match.")
        return None
    if not re.fullmatch(r'"[1-9][0-9]*"', value):
        raise ConfigurationError('Use the exact quoted ETag, such as --if-match \x27"3"\x27.')
    return value


def parse_duration(raw: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([smhd]?)", raw)
    if not match:
        raise ConfigurationError("Use a positive duration such as 30s, 5m, or 1h.")
    return int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]


def resource_output(value: Any, *, access: bool) -> Any:
    if access and isinstance(value, dict):
        if "items" in value and isinstance(value["items"], list):
            return {**value, "items": [resource_output(item, access=access) for item in value["items"]]}
        if {"id", "kind", "project", "state", "version", "spec"} <= value.keys():
            AccessResource.model_validate(value)
            return {**value, "etag": '"' + str(value["version"]) + '"'}
    return value


def _body(spec: CommandSpec, values: dict) -> dict | None:
    kind = spec.body
    if kind is None:
        return None
    if kind == "service" and not values.get("project_wide_credential"):
        raise ConfigurationError("Acknowledge shared project credentials with --project-wide-credential.")
    if kind == "secret":
        return {"value": read_secret(values.get("value_file"))}
    if values.get("file"):
        return read_json(values["file"])
    if kind == "file":
        if spec.command == "data-services recovery request" and values.get("reason"):
            return {"reason": values["reason"]}
        if spec.command == "operator recovery-requests review" and values.get("status"):
            return {"status": values["status"]}
        raise ConfigurationError("Supply a complete JSON document with --file PATH or --file -.")
    if kind == "groups":
        groups = values.get("group") or []
        if not groups:
            raise ConfigurationError("Supply at least one --group ID or name.")
        return {"groups": groups}
    if kind == "service":
        return {"name": require(values, "name"), "providerProject": require(values, "provider_project"),
                "application": require(values, "application"), "projectWideCredential": True}
    if kind == "group":
        return {"name": require(values, "name"), "displayName": require(values, "display_name")}
    if kind == "project":
        return {"name": require(values, "project")}
    if kind == "revision":
        return {"revision": int(require(values, "revision"))}
    if kind == "rotation":
        return {"emergency": bool(values.get("emergency"))}
    if kind == "retirement":
        return {"confirm_name": require(values, "project"), "scope_token": require(values, "scope_token")}
    if kind == "grant":
        result = {"issuer": require(values, "issuer"), "subject": require(values, "subject")}
        if spec.method == "PUT":
            result["role"] = require(values, "role")
            if values.get("display_name"):
                result["display_name"] = values["display_name"]
        return result
    if kind == "credential":
        body = {key: values[key] for key in spec.fields if values.get(key) is not None}
        if "name" in spec.fields:
            body["name"] = require(values, "name")
        for key in ("expires_in_days", "overlap_hours", "expires_in_hours"):
            if key in body:
                body[key] = int(body[key])
        return body
    raise ConfigurationError("Unknown command request body.")


def require(values: dict, key: str) -> Any:
    value = values.get(key)
    if value is None or value == "":
        raise ConfigurationError("Supply --" + key.replace("_", "-") + ".")
    return value


def _path(spec: CommandSpec, values: dict) -> str:
    def replacement(match):
        key = match.group(1)
        val = require(values, "project" if key in {"project", "name"} and spec.path != "/projects" else key)
        if not re.fullmatch(r"[A-Za-z0-9._-]+", str(val)):
            raise ConfigurationError("Invalid resource identifier in API path.")
        return quote(str(val), safe="")
    return re.sub(r"\{([a-z_]+)\}", replacement, spec.path)


def _query(spec: CommandSpec, values: dict) -> dict:
    return {"since_seconds" if key == "since" else key: parse_duration(values[key]) if key == "since" else
            int(values[key]) if key in {"tail", "limit"} else values[key]
            for key in spec.query if values.get(key) is not None}


def _automatic_etag(spec: CommandSpec, client: PlatformClient, path: str, values: dict) -> str | None:
    supplied = etag(values.get("if_match"))
    if supplied:
        return supplied
    if spec.version == "required":
        if not sys.stdin.isatty():
            return etag(None, required=True)
        project = require(values, "project") if "{project}" in spec.path else None
        if spec.command.startswith("access services"):
            collection = "/v1/projects/" + quote(project, safe="") + "/service-access-requests"
            data, _ = client.request_json("GET", collection)
            resource = next((item for item in data.get("items", []) if item.get("id") == values.get("resource_id")), None)
        elif spec.command.startswith("access human-requests"):
            data, _ = client.request_json("GET", "/v1/projects/" + quote(project, safe="") + "/application-access-requests")
            resource = next((item for item in data.get("items", []) if item.get("id") == values.get("resource_id")), None)
        elif spec.command == "access operations retry":
            raise ConfigurationError("Supply the failed resource's ETag with --if-match.")
        else:
            raise ConfigurationError("Supply the current resource ETag with --if-match.")
        if resource is None:
            raise ApiError(404, "The access resource was not found in the selected project.")
        return etag('"' + str(resource["version"]) + '"', required=True)
    if spec.version == "optional":
        try:
            current, observed = client.request_json("GET", path)
            if isinstance(current, dict) and "version" in current:
                return etag(observed or '"' + str(current["version"]) + '"')
        except ApiError as error:
            if error.status_code != 404:
                raise
    return None


def watch_access(client: PlatformClient, operation_id: str, timeout: float, interval: float,
                 progress) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        raw, _ = client.request_json("GET", "/v1/access-operations/" + quote(operation_id, safe=""))
        status = AccessOperation.model_validate(raw)
        progress(status.state)
        if status.state in {"failed", "cancelled"}:
            raise AccessOperationFailed(operation_id, status.errorCode or status.state)
        if status.state == "succeeded":
            return raw
        if time.monotonic() >= deadline:
            raise OperationTimeout(operation_id)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def execute(spec: CommandSpec, state, values: dict):
    output = values.get("output") or state.output or "table"
    if output not in {"table", "plain", "json"}:
        raise ConfigurationError("Use --output table, plain, or json.")
    client = None
    try:
        config = runtime_config(profile_name=state.profile, api_url_override=state.api_url, insecure=state.insecure)
        if not values.get("output") and not state.output and config.profile is not None:
            output = config.profile.output
        if not values.get("project") and config.profile is not None:
            values["project"] = config.profile.project
        client = PlatformClient(config)
        client.debug = state.debug
        path = _path(spec, values)
        if spec.command.startswith("secrets ") and values.get("secret", "").startswith("ACCESS_"):
            raise ConfigurationError("Managed service credentials must be changed with access services commands.")
        if spec.destructive and not values.get("confirm_project"):
            raise ConfigurationError("Confirm the exact project/scope with --confirm-project NAME.")
        if spec.destructive and values["confirm_project"] != (values.get("project") or "platform"):
            raise ConfigurationError("The confirmation scope does not match this request.")
        body = _body(spec, values)
        headers = {}
        if spec.version:
            version = _automatic_etag(spec, client, path, values)
            if version:
                headers["If-Match"] = version
        if spec.idempotent:
            key = values.get("idempotency_key") or str(uuid4())
            headers["Idempotency-Key"] = key
            typer.echo("Idempotency key: " + key, err=True)
        if spec.command == "operator audit export" and values.get("format") == "csv":
            typer.echo(client.request_text("GET", path, params=_query(spec, values)), nl=False)
            return
        result, observed_etag = client.request_json(spec.method, path, body=body,
            params=_query(spec, values) or None, headers=headers)
        if spec.access_resource:
            result = resource_output(result, access=True)
        if spec.command == "access services list" and values.get("direction"):
            direction = values["direction"]
            if direction not in {"incoming", "outgoing"}:
                raise ConfigurationError("Use --direction incoming or outgoing.")
            project = values["project"]
            result = {**result, "items": [item for item in result["items"] if
                (item["spec"]["providerProject"] == project if direction == "incoming" else item["project"] == project)]}
        if observed_etag and isinstance(result, dict) and "etag" not in result:
            result = {**result, "etag": observed_etag}
        if values.get("wait") and isinstance(result, dict) and result.get("status_url"):
            timeout = float(values.get("timeout") or 300)
            interval = float(values.get("poll_interval") or 2)
            if timeout <= 0 or interval <= 0:
                raise ConfigurationError("Wait timeout and polling interval must be positive.")
            if spec.family == "access":
                operation = result.get("operation_id")
                if not isinstance(operation, str):
                    raise ApiError(503, "The platform returned an invalid access operation ID.")
                status = watch_access(client, operation, timeout, interval,
                    lambda s: typer.echo("Access operation " + operation + ": " + s, err=True)
                    if output != "json" and not state.quiet else None)
                if isinstance(result.get("id"), str):
                    if spec.command.startswith("access services"):
                        collection = "/v1/projects/" + quote(values["project"], safe="") + "/service-access-requests"
                    elif spec.command.startswith("access groups"):
                        collection = "/v1/projects/" + quote(values["project"], safe="") + "/application-groups"
                    elif spec.command.startswith("access memberships"):
                        collection = "/v1/projects/" + quote(values["project"], safe="") + "/application-group-memberships"
                    else:
                        collection = None
                    if collection:
                        rows, _ = client.request_json("GET", collection)
                        observed = next((item for item in rows.get("items", []) if item.get("id") == result["id"]), None)
                    elif spec.command.startswith("access policy"):
                        observed, _ = client.request_json("GET", "/v1/projects/" + quote(values["project"], safe="") +
                            "/applications/" + quote(values["application"], safe="") + "/access-policy")
                    else:
                        observed = None
                    if observed:
                        result = resource_output(observed, access=True)
                result = {**result, "operation": status}
            elif spec.family == "deployment":
                accepted = OperationAccepted.model_validate({key: result[key] for key in
                    ("operation_id", "state", "revision", "status_url")})
                token = client.access_token()
                status = wait_for_operation(client, accepted, token, timeout, interval,
                    time.monotonic, time.sleep, lambda s: typer.echo("Operation " + s.operation_id + ": " + s.state, err=True)
                    if output != "json" and not state.quiet else None)
                result = status.model_dump()
        if spec.command == "stores access credential":
            typer.echo("Sensitive credential material: keep it in a protected secret store.", err=True)
        elif spec.credential:
            typer.echo("Credential material is returned once; store it in a protected secret store.", err=True)
        emit(result, output, one_time=spec.credential)
        if spec.command == "logs" and values.get("follow"):
            cursor = result.get("next_cursor") if isinstance(result, dict) else None
            while True:
                time.sleep(float(values.get("poll_interval") or 2))
                query = _query(spec, values)
                if cursor:
                    query["after"] = cursor
                update, _ = client.request_json("GET", path, params=query)
                cursor = update.get("next_cursor") or cursor
                if update.get("lines"):
                    emit(update, output)
    except KeyboardInterrupt:
        typer.echo("Local following stopped; server state is unchanged.", err=True)
        raise typer.Exit(10) from None
    except (ApiError, ConfigurationError, OperationTimeout, OperationFailed, AccessOperationFailed,
            ValueError, OSError) as error:
        secret_values = (body.get("value"),) if isinstance(locals().get("body"), dict) and "value" in body else ()
        raise fail(error, output, secret_values) from None
    finally:
        if client is not None:
            client.close()


def register(app: typer.Typer, spec: CommandSpec):
    """Expose only the options relevant to this operation, retaining domain names."""
    positional = [name for name in ("resource_id", "credential_id", "operation_id", "request_id", "secret",
                                   "trace_id", "run_id", "proposal_id", "grant_id") if "{" + name + "}" in spec.path]
    params = [inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=typer.Context)]
    for name in positional:
        params.append(inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=typer.Argument(...), annotation=str))
    options = []
    if "{name}" in spec.path or "{project}" in spec.path or spec.body in {"project", "retirement"}:
        options.append("project")
    if "{application}" in spec.path:
        options.append("application")
    options += list(spec.fields)
    if spec.body and spec.body != "secret":
        options.append("file")
    if spec.body == "secret":
        options.append("value_file")
    if spec.version:
        options.append("if_match")
    if spec.idempotent:
        options.append("idempotency_key")
    options += list(spec.query)
    if spec.command == "access services list":
        options.append("direction")
    if spec.command == "logs":
        options.extend(("follow", "poll_interval"))
    if spec.destructive:
        options.append("confirm_project")
    if spec.family and spec.method != "GET":
        options.extend(("wait", "timeout", "poll_interval"))
    options.append("output")
    for name in dict.fromkeys(options):
        declaration = "--" + name.replace("_", "-")
        annotation = list[str] | None if name == "group" else bool if name in {"wait", "emergency", "project_wide_credential", "follow"} else str | None
        default = False if annotation is bool else None
        params.append(inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=typer.Option(default, declaration), annotation=annotation))

    def command(**kwargs):
        ctx = kwargs.pop("ctx")
        if spec.command == "logs" and ctx.invoked_subcommand:
            return
        execute(spec, context_state(ctx), kwargs)

    command.__name__ = "command_" + spec.command.replace(" ", "_").replace("-", "_")
    command.__doc__ = spec.description
    command.__signature__ = inspect.Signature(params)
    if spec.command == "logs":
        app.info.no_args_is_help = False
        app.callback(invoke_without_command=True)(command)
    else:
        app.command(spec.command.split()[-1])(command)
