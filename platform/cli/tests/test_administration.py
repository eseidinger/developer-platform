"""Exercise public administration commands across the transport boundary."""

import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from platform_cli.__main__ import app
from platform_cli.client import PlatformClient
from platform_cli.profiles import Profile, ProfileStore
from platform_cli.registry import COMMANDS, EXCLUSIONS


def _cli(monkeypatch, tmp_path, handler):
    monkeypatch.setenv("DEVPLAT_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("PLATFORM_API_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ACCESS_TOKEN", "human-token")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("platform_cli.commands.PlatformClient", lambda config: PlatformClient(config, client))
    monkeypatch.setattr("platform_cli.__main__.PlatformClient", lambda config: PlatformClient(config, client))
    return CliRunner()


def _resource(state="pending", version=1):
    return {"id": "svc_1", "kind": "service-access", "name": "worker-api", "project": "orders",
            "state": state, "version": version, "spec": {"providerProject": "orders", "application": "orders"}}


def test_same_project_request_approval_and_wait(monkeypatch, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer human-token"
        if request.method == "POST" and request.url.path.endswith("/service-access-requests"):
            assert request.headers["idempotency-key"] == "orders-worker-api"
            assert json.loads(request.content) == {"name": "worker-api", "providerProject": "orders",
                                                   "application": "orders", "projectWideCredential": True}
            return httpx.Response(201, json=_resource(), headers={"ETag": '"1"'})
        if request.method == "POST" and request.url.path.endswith("/svc_1/approve"):
            assert request.headers["if-match"] == '"1"'
            assert json.loads(request.content) == {"groups": ["grp_123"]}
            return httpx.Response(202, json={**_resource("provisioning", 2),
                "operation_id": "op-1", "status_url": "/v1/access-operations/op-1"})
        if request.url.path == "/v1/access-operations/op-1":
            return httpx.Response(200, json={"id": "op-1", "resourceId": "svc_1", "state": "succeeded",
                                              "attempts": 1, "errorCode": None})
        if request.method == "GET" and request.url.path.endswith("/service-access-requests"):
            return httpx.Response(200, json={"items": [{**_resource("active", 3),
                "spec": {**_resource()["spec"], "secretPrefix": "ACCESS_123",
                         "providerUrl": "https://api-orders.example", "audience": "app-1"}}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    runner = _cli(monkeypatch, tmp_path, handler)
    created = runner.invoke(app, ["access", "services", "request", "--project", "orders", "--name", "worker-api",
        "--provider-project", "orders", "--application", "orders", "--project-wide-credential",
        "--idempotency-key", "orders-worker-api", "--output", "json"])
    assert created.exit_code == 0, created.output
    assert json.loads(created.stdout)["etag"] == '"1"'
    approved = runner.invoke(app, ["access", "services", "approve", "svc_1", "--project", "orders",
        "--group", "grp_123", "--if-match", '"1"', "--wait", "--output", "json"])
    assert approved.exit_code == 0, approved.output
    result = json.loads(approved.stdout)
    assert result["state"] == "active"
    assert result["spec"]["secretPrefix"] == "ACCESS_123"
    assert result["operation"]["state"] == "succeeded"
    assert "CLIENT_SECRET" not in approved.output


def test_stale_etag_denial_and_missing_precondition(monkeypatch, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(412, json={"detail": "Stale resource", "code": "stale"})

    runner = _cli(monkeypatch, tmp_path, handler)
    missing = runner.invoke(app, ["access", "services", "approve", "svc_1", "--project", "orders",
                                   "--group", "grp_123", "--output", "json"])
    assert missing.exit_code == 2
    assert not requests
    stale = runner.invoke(app, ["access", "services", "approve", "svc_1", "--project", "orders",
                                 "--group", "grp_123", "--if-match", '"1"', "--output", "json"])
    assert stale.exit_code == 6
    assert json.loads(stale.stderr)["status"] == 412
    assert len(requests) == 1


def test_unauthorized_admin_action_is_reported_without_replay(monkeypatch, tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(403, json={"detail": "Not authorized for this operation"})

    runner = _cli(monkeypatch, tmp_path, handler)
    result = runner.invoke(app, ["access", "groups", "create", "--project", "orders", "--name", "workers",
        "--display-name", "Workers", "--idempotency-key", "workers-1", "--output", "json"])
    assert result.exit_code == 4
    assert len(seen) == 1
    assert json.loads(result.stderr.splitlines()[-1])["status"] == 403


def test_failed_access_operation_has_durable_failure_exit(monkeypatch, tmp_path):
    def handler(request):
        assert request.url.path == "/v1/access-operations/op-1"
        return httpx.Response(200, json={"id": "op-1", "resourceId": "svc_1", "state": "failed",
                                          "errorCode": "provider_unavailable", "attempts": 3})

    runner = _cli(monkeypatch, tmp_path, handler)
    result = runner.invoke(app, ["access", "operations", "watch", "op-1", "--output", "json"])
    assert result.exit_code == 9
    assert "op-1" in result.stderr


def test_managed_access_secret_cannot_be_overwritten_by_generic_secret_command(monkeypatch, tmp_path):
    def handler(request):
        raise AssertionError("Managed secret command must not call the API")

    runner = _cli(monkeypatch, tmp_path, handler)
    result = runner.invoke(app, ["secrets", "set", "ACCESS_ABC_CLIENT_SECRET", "--project", "orders",
                                 "--value-file", "-"] , input="bad-value\n")
    assert result.exit_code == 2
    assert "bad-value" not in result.output


def test_configuration_replacement_wait_accepts_operation_metadata(monkeypatch, tmp_path):
    def handler(request):
        assert request.headers["authorization"] == "Bearer human-token"
        if request.method == "PUT":
            assert request.url.path == "/projects/orders/configuration"
            assert request.headers["if-match"] == '"3"'
            assert json.loads(request.content) == {"values": {"MODE": "ready"}}
            return httpx.Response(202, json={"operation_id": "op-config", "state": "queued",
                "revision": 4, "rollout_required": True, "status_url": "/v1/operations/op-config"})
        assert request.url.path == "/v1/operations/op-config"
        return httpx.Response(200, json={"operation_id": "op-config", "state": "succeeded",
            "revision": 4, "readiness": {"state": "ready"}})

    runner = _cli(monkeypatch, tmp_path, handler)
    result = runner.invoke(app, ["config", "replace", "--project", "orders", "--file", "-",
        "--if-match", '"3"', "--wait", "--output", "json"], input='{"values":{"MODE":"ready"}}')
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["readiness"]["state"] == "ready"


def test_operator_audit_csv_export(monkeypatch, tmp_path):
    def handler(request):
        assert request.url.path == "/operator/audit/events"
        assert request.url.params["format"] == "csv"
        assert request.url.params["limit"] == "20"
        return httpx.Response(200, text="id,action\n1,project.created\n", headers={"content-type": "text/csv"})

    runner = _cli(monkeypatch, tmp_path, handler)
    result = runner.invoke(app, ["operator", "audit", "export", "--start", "2026-10-01T00:00:00Z",
        "--end", "2026-10-02T00:00:00Z", "--format", "csv", "--limit", "20"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "id,action\n1,project.created\n"


def test_profile_default_project_and_output(monkeypatch, tmp_path):
    monkeypatch.setenv("DEVPLAT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("PLATFORM_API_URL", raising=False)
    monkeypatch.setenv("PLATFORM_ACCESS_TOKEN", "human-token")
    ProfileStore().create("lab", Profile("https://platform.example", "https://identity.example/realms/platform",
                                         project="orders", output="json"))

    def handler(request):
        assert request.url.path == "/projects"
        return httpx.Response(200, json=[{"name": "orders", "status": "active"}])

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("platform_cli.__main__.PlatformClient", lambda config: PlatformClient(config, transport))
    result = CliRunner().invoke(app, ["projects", "show"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"name": "orders", "status": "active"}


def test_public_contract_has_a_domain_command_for_every_operation():
    source = json.loads((Path(__file__).resolve().parents[3] / "docs/api/openapi.json").read_text())
    paths = {(method.upper(), path) for path, operations in source["paths"].items()
             for method in operations if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}}
    assert paths == {(item.method, item.path) for item in COMMANDS} | EXCLUSIONS.keys()
