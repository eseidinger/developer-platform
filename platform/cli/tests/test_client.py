import httpx

from platform_cli.client import PlatformClient, wait_for_operation
from platform_cli.config import runtime_config
from platform_cli.models import OperationAccepted


def test_deployment_credential_exchange_and_apply_use_bearer_token():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "identity.example":
            return httpx.Response(200, json={"access_token": "short-lived", "token_type": "Bearer"})
        return httpx.Response(202, json={
            "operation_id": "operation-1", "state": "queued", "revision": 1, "status_url": "/v1/operations/operation-1",
        })

    config = runtime_config({
        "PLATFORM_API_URL": "https://platform.example",
        "PLATFORM_TOKEN_ENDPOINT": "https://identity.example/token",
        "PLATFORM_CLIENT_ID": "client-id",
        "PLATFORM_CLIENT_SECRET": "client-secret",
    })
    client = PlatformClient(config, httpx.Client(transport=httpx.MockTransport(handler)))

    token = client.access_token()
    accepted = client.deploy("smoke", {"name": "smoke", "image": "example/image:1"}, token)

    assert accepted.operation_id == "operation-1"
    assert requests[0].url == "https://identity.example/token"
    assert requests[1].headers["authorization"] == "Bearer short-lived"


def test_wait_requires_apply_success_and_readiness():
    responses = iter([
        {"operation_id": "operation-1", "revision": 1, "state": "running", "error_code": None, "readiness": {"state": "progressing", "reason": "pods_not_ready"}},
        {"operation_id": "operation-1", "revision": 1, "state": "succeeded", "error_code": None, "readiness": {"state": "ready", "reason": None}},
    ])

    class FakeClient:
        def operation(self, _url: str, _token: str):
            from platform_cli.models import OperationStatus
            return OperationStatus.model_validate(next(responses))

    ticks = iter([0.0, 0.0, 1.0])
    updates = []
    completed = wait_for_operation(
        FakeClient(), OperationAccepted(operation_id="operation-1", state="queued", revision=1, status_url="/v1/operations/operation-1"),
        "token", 10.0, 1.0, lambda: next(ticks), lambda _seconds: None, updates.append,
    )

    assert completed.readiness.state == "ready"
    assert len(updates) == 2


def test_ai_run_waits_for_server_budget_and_never_retries_post():
    from platform_cli.errors import ApiError
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout('fixture timeout', request=request)

    config = runtime_config({'PLATFORM_API_URL': 'https://platform.example', 'PLATFORM_ACCESS_TOKEN': 'fixture-token'})
    client = PlatformClient(config, httpx.Client(transport=httpx.MockTransport(handler), timeout=30))
    try:
        client.request_json('POST', '/projects/demo/ai/runs', body={'kind': 'investigate_incident'})
    except ApiError:
        pass
    else:
        raise AssertionError('Expected timeout error')
    assert len(requests) == 1
    assert requests[0].extensions['timeout']['read'] == 120
    assert requests[0].extensions['timeout']['connect'] == 5
