import json

import httpx
from platform_cli.__main__ import app
from platform_cli.client import PlatformClient
from typer.testing import CliRunner


def test_auth_status_reports_environment_source_without_token(monkeypatch):
    monkeypatch.setenv("PLATFORM_API_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ACCESS_TOKEN", "should-not-appear")

    result = CliRunner().invoke(app, ["auth", "status", "--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "source": "access-token-environment",
        "persistent": False,
    }
    assert "should-not-appear" not in result.output


def test_existing_deploy_apply_works_with_environment_auth_and_broken_profile(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DEVPLAT_CONFIG_DIR", str(tmp_path))
    (tmp_path / "profiles.toml").write_text("invalid = [", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_API_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ACCESS_TOKEN", "existing-token")
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "PUT"
        assert request.url.path == "/projects/orders"
        assert request.headers["authorization"] == "Bearer existing-token"
        assert request.headers["if-match"] == '"2"'
        assert json.loads(request.content) == {"name": "orders", "components": []}
        return httpx.Response(
            202,
            json={
                "operation_id": "op-1",
                "state": "queued",
                "revision": 3,
                "status_url": "/v1/operations/op-1",
            },
        )

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        "platform_cli.__main__.PlatformClient",
        lambda config: PlatformClient(config, transport),
    )
    result = CliRunner().invoke(
        app,
        [
            "deploy",
            "apply",
            "--project",
            "orders",
            "--file",
            "-",
            "--if-match",
            '"2"',
            "--output",
            "json",
        ],
        input='{"name":"orders","components":[]}',
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["revision"] == 3
    assert len(seen) == 1
    assert "existing-token" not in result.output


def test_operations_watch_resumes_an_existing_operation(monkeypatch, tmp_path):
    monkeypatch.setenv("DEVPLAT_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("PLATFORM_API_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ACCESS_TOKEN", "existing-token")
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/operations/op-1"
        assert request.headers["authorization"] == "Bearer existing-token"
        return httpx.Response(
            200,
            json={
                "operation_id": "op-1",
                "state": "succeeded",
                "revision": 3,
                "readiness": {"state": "ready"},
            },
        )

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        "platform_cli.__main__.PlatformClient",
        lambda config: PlatformClient(config, transport),
    )
    result = CliRunner().invoke(
        app, ["operations", "watch", "op-1", "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["operation_id"] == "op-1"
    assert len(seen) == 2
    assert "existing-token" not in result.output
