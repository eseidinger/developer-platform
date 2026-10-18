"""Exercise public administration commands across the transport boundary."""

import json
from pathlib import Path

import httpx
import pytest
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


@pytest.mark.parametrize("arguments,path,params", [
    (["metrics", "get", "--component", "web"], "/projects/orders/application-metrics", {"component": "web"}),
    (["traces", "get", "a" * 32], "/projects/orders/traces/" + "a" * 32, {}),
    (["ai", "policy", "get"], "/projects/orders/ai/policy", {}),
    (["ai", "runs", "get", "run-1"], "/projects/orders/ai/runs/run-1", {}),
    (["ai", "proposals", "get", "proposal-1"], "/projects/orders/ai/proposals/proposal-1", {}),
])
def test_telemetry_and_ai_reads_preserve_project_ids_and_query(monkeypatch, tmp_path, arguments, path, params):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == path
        assert dict(request.url.params) == params
        assert request.headers["authorization"] == "Bearer human-token"
        return httpx.Response(200, json={"project": "orders", "state": "ok"})

    runner = _cli(monkeypatch, tmp_path, handler)
    result = runner.invoke(app, arguments + ["--project", "orders", "--output", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["project"] == "orders"


@pytest.mark.parametrize("arguments,method,suffix,body,confirm", [
    (["ai", "policy", "replace"], "PUT", "policy", {"classification": "internal"}, True),
    (["ai", "runs", "create"], "POST", "runs", {"kind": "investigate_incident"}, False),
    (["ai", "proposals", "create"], "POST", "proposals", {"run_id": "run-1"}, False),
    (["ai", "proposals", "approve", "proposal-1"], "POST", "proposals/proposal-1/approval",
     {"diff_sha256": "a" * 64}, True),
    (["ai", "proposals", "execute", "proposal-1"], "POST", "proposals/proposal-1/execute",
     {"diff_sha256": "a" * 64}, True),
])
def test_ai_mutations_send_exact_reviewed_document(monkeypatch, tmp_path, arguments, method, suffix, body, confirm):
    document = tmp_path / "request.json"
    document.write_text(json.dumps(body))

    def handler(request):
        assert request.method == method
        assert request.url.path == "/projects/orders/ai/" + suffix
        assert json.loads(request.content) == body
        return httpx.Response(200, json={"project": "orders", "state": "succeeded"})

    runner = _cli(monkeypatch, tmp_path, handler)
    options = ["--confirm-project", "orders"] if confirm else []
    result = runner.invoke(app, arguments + ["--project", "orders", "--file", str(document),
                                            "--output", "json"] + options)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("action", ["approve", "execute"])
def test_ai_approval_and_execution_require_project_confirmation(monkeypatch, tmp_path, action):
    requests = []
    runner = _cli(monkeypatch, tmp_path, lambda request: requests.append(request))
    result = runner.invoke(app, ["ai", "proposals", action, "proposal-1", "--project", "orders",
                                 "--file", "not-read-without-confirmation.json"])
    assert result.exit_code == 2, result.output
    assert "--confirm-project" in result.output
    assert not requests


def test_obsolete_database_issuance_commands_are_excluded():
    commands = {item.command for item in COMMANDS}
    assert "database-access grants create" not in commands
    assert "database-access credential issue" not in commands
    assert ("POST", "/projects/{name}/database-access/grants") in EXCLUSIONS
    assert ("POST", "/projects/{name}/database-access/me/credential") in EXCLUSIONS


@pytest.mark.parametrize("provider", ["postgresql", "s3", "qdrant", "opensearch", "neo4j"])
def test_store_tunnel_uses_verified_host_and_does_not_print_credential(monkeypatch, tmp_path, provider):
    from uuid import uuid4

    credential_id = str(uuid4())
    key = tmp_path / "id_ed25519"
    key.write_text("private key")
    key.chmod(0o600)
    hosts = tmp_path / "known_hosts"
    hosts.write_text("bastion.example ssh-ed25519 verified-key\n")
    commands = []

    def handler(request):
        assert request.url.path == "/v1/store-access/credentials/" + credential_id
        return httpx.Response(200, json={"state": "active", "provider": provider,
            "connection": {"PGPASSWORD": "never-print-me"},
            "ssh": {"user": "platform-db", "host": "bastion.example", "port": 2222,
                    "destination": "172.30.80.15", "destination_port": 20001}})

    runner = _cli(monkeypatch, tmp_path, handler)
    monkeypatch.setattr("platform_cli.tunnel.subprocess.run", lambda command, check: commands.append(command) or type("Result", (), {"returncode": 0})())
    result = runner.invoke(app, ["stores", "access", "tunnel", credential_id,
        "--identity-file", str(key), "--known-hosts", str(hosts), "--local-port", "15432"])
    assert result.exit_code == 0, result.output
    assert commands[0][-3:] == ["-L", "127.0.0.1:15432:172.30.80.15:20001", "platform-db@bastion.example"]
    assert "StrictHostKeyChecking=yes" in commands[0]
    assert "never-print-me" not in result.output
    assert "never-print-me" not in repr(commands[0])


@pytest.mark.parametrize(("command", "target", "confirmation"), [
    (["retire", "resource-1"], "resource-1", "--confirm-resource-id"),
    (["purge", "resource-1"], "resource-1", "--confirm-resource-id"),
    (["grants", "revoke", "grant-1"], "grant-1", "--confirm-grant-id"),
])
def test_destructive_store_commands_require_exact_target_confirmation(monkeypatch, tmp_path, command, target, confirmation):
    requests = []
    runner = _cli(monkeypatch, tmp_path, lambda request: requests.append(request) or httpx.Response(202, json={"state": "retired"}))
    body = tmp_path / "version.json"
    body.write_text('{"version": 1}')
    args = ["stores", *command, "--file", str(body)]
    missing = runner.invoke(app, args)
    assert missing.exit_code == 2, missing.output
    assert confirmation in missing.output
    wrong = runner.invoke(app, [*args, confirmation, "other-id"])
    assert wrong.exit_code == 2, wrong.output
    assert requests == []
    confirmed = runner.invoke(app, [*args, confirmation, target])
    assert confirmed.exit_code == 0, confirmed.output
    assert len(requests) == 1


@pytest.mark.parametrize("credential", [
    {"state": "issuing", "provider": "postgresql"},
    {"state": "active", "provider": "postgresql"},
    {"state": "active", "provider": "neo4j", "ssh": {"user": "platform-db"}},
])
def test_tunnel_rejects_unusable_lease_before_ssh(monkeypatch, tmp_path, credential):
    from uuid import uuid4

    credential_id = str(uuid4())
    runner = _cli(monkeypatch, tmp_path, lambda request: httpx.Response(200, json=credential))
    monkeypatch.setattr("platform_cli.tunnel.subprocess.run", lambda *args, **kwargs: pytest.fail("SSH must not run"))
    result = runner.invoke(app, ["stores", "access", "tunnel", credential_id,
        "--identity-file", str(tmp_path / "key"), "--known-hosts", str(tmp_path / "hosts"),
        "--local-port", "15432"])
    assert result.exit_code == 2, result.output


def test_tunnel_rejects_untrusted_endpoint_and_exposed_key(monkeypatch, tmp_path):
    from uuid import uuid4

    credential_id = str(uuid4())
    key = tmp_path / "id_ed25519"
    key.write_text("private key")
    key.chmod(0o600)
    hosts = tmp_path / "known_hosts"
    hosts.write_text("bastion.example ssh-ed25519 verified-key\n")
    credential = {"state": "active", "provider": "postgresql",
        "ssh": {"user": "platform-db", "host": "-oProxyCommand=sh", "port": 2222,
                "destination": "172.30.80.15", "destination_port": 20001}}
    runner = _cli(monkeypatch, tmp_path, lambda request: httpx.Response(200, json=credential))
    monkeypatch.setattr("platform_cli.tunnel.subprocess.run", lambda *args, **kwargs: pytest.fail("SSH must not run"))
    args = ["stores", "access", "tunnel", credential_id, "--identity-file", str(key),
            "--known-hosts", str(hosts), "--local-port", "15432"]
    assert runner.invoke(app, args).exit_code == 2
    credential["ssh"]["host"] = "bastion.example"
    key.chmod(0o644)
    assert runner.invoke(app, args).exit_code == 2
