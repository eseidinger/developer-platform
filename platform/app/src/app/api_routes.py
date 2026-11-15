"""Register response models and errors together with each public API route."""

from functools import wraps

from fastapi.datastructures import DefaultPlaceholder
from fastapi.routing import APIRoute

from .response_models import ErrorResponse, model_for

CREATED = {
    "create_empty_project",
    "create_deployment_credential",
    "rotate_deployment_credential",
    "create_test_runner_credential",
    "rotate_test_runner_credential",
    "create_test_identity",
}
ACCEPTED = {
    "provision",
    "put_configuration",
    "set_secret",
    "delete_secret",
    "revert_secret_rotation",
    "rollback",
    "restart",
}


# Ordinary API calls share this lock. Lifecycle acceptance and worker steps take
# it exclusively so no admitted request can recreate records after their sweep.
LIFECYCLE_HTTP_LOCK = 731926


def lifecycle_fenced(endpoint, exclusive=False):
    @wraps(endpoint)
    def guarded(*args, **kwargs):
        from . import main

        suffix = "" if exclusive else "_shared"
        with main.connect() as conn:
            conn.execute(
                "SELECT pg_advisory_lock" + suffix + "(%s)", (LIFECYCLE_HTTP_LOCK,)
            )
            try:
                return endpoint(*args, **kwargs)
            finally:
                conn.execute(
                    "SELECT pg_advisory_unlock" + suffix + "(%s)",
                    (LIFECYCLE_HTTP_LOCK,),
                )

    return guarded


class ContractRoute(APIRoute):
    def __init__(self, path, endpoint, **kwargs):
        if kwargs.get("include_in_schema", True):
            supplied = kwargs.get("response_model")
            model = (
                model_for(endpoint)
                if supplied is None or isinstance(supplied, DefaultPlaceholder)
                else supplied
            )
            if model is None:
                raise ValueError(
                    "Public endpoint needs a response contract: "
                    + endpoint.__module__
                    + "."
                    + endpoint.__name__
                )
            kwargs["response_model"] = model
            if endpoint.__name__ in CREATED:
                kwargs["status_code"] = 201
            elif endpoint.__name__ in ACCEPTED:
                kwargs["status_code"] = 202
            responses = dict(kwargs.get("responses") or {})
            if path not in {"/healthz", "/readyz"}:
                for code, description in {
                    400: "Invalid request",
                    401: "Authentication required",
                    403: "Permission denied",
                    404: "Resource unavailable",
                    409: "State or revision conflict",
                    412: "ETag mismatch",
                    422: "Validation failed",
                    428: "Precondition required",
                    503: "Platform dependency unavailable",
                }.items():
                    responses.setdefault(
                        code, {"model": ErrorResponse, "description": description}
                    )
            if (
                endpoint.__name__.startswith("revoke_")
                and "credential" in endpoint.__name__
                or endpoint.__name__ == "revoke_test_identity"
            ):
                responses[202] = {
                    "model": model,
                    "description": "Credential revocation accepted",
                }
            if endpoint.__name__ in {"create_group", "request_service"}:
                responses[200] = {"model": model, "description": "Idempotent replay"}
            if endpoint.__name__ == "export_audit_events":
                responses[200] = {
                    "model": model,
                    "content": {"text/csv": {"schema": {"type": "string"}}},
                }
            kwargs["responses"] = responses
        if path.startswith("/v1/") and path != "/v1/capabilities":
            exclusive = endpoint.__module__.endswith(
                ".lifecycle.api"
            ) and endpoint.__name__ in {"retire", "restore", "purge"}
            endpoint = lifecycle_fenced(endpoint, exclusive)
        super().__init__(path, endpoint, **kwargs)
