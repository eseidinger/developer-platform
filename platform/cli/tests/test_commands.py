import json

from typer.testing import CliRunner

from platform_cli.__main__ import app


def test_auth_status_reports_environment_source_without_token(monkeypatch):
    monkeypatch.setenv("PLATFORM_API_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ACCESS_TOKEN", "should-not-appear")

    result = CliRunner().invoke(app, ["auth", "status", "--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"source": "access-token-environment", "persistent": False}
    assert "should-not-appear" not in result.output
