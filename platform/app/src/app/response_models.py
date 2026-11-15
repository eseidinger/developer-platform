"""Public response contracts shared by route registration and generated clients.

Provider observations and AI evidence contain structured JSON extensions. Their
known envelope fields are typed here while those extension objects stay JSON.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, create_model

Object = dict[str, JsonValue]


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ErrorResponse(BaseModel):
    detail: str | list[Object] | Object
    code: str


class ProjectSummary(ResponseModel):
    name: str
    status: str
    project_id: UUID | None = None


class OperationAccepted(ResponseModel):
    operation_id: str
    state: str
    revision: int
    status_url: str


class Readiness(ResponseModel):
    state: str
    reason: str | None = None


class DeploymentOperation(ResponseModel):
    operation_id: str
    kind: Literal["deployment"]
    state: str
    revision: int
    error_code: str | None
    result: JsonValue
    readiness: Readiness


class AccessOperation(ResponseModel):
    operation_id: str
    kind: Literal["access"]
    state: str
    resource_id: str
    error_code: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime


class LifecycleOperation(ResponseModel):
    operation_id: UUID
    project_id: UUID
    project: str
    kind: Literal["retire", "restore", "purge"]
    state: Literal["queued", "running", "blocked", "failed", "succeeded"]
    step: str
    result: Object
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class AccessResource(ResponseModel):
    id: str
    kind: str
    project: str
    name: str
    state: str
    version: int
    spec: Object
    created_at: datetime
    updated_at: datetime
    operation_id: str | None = None
    status_url: str | None = None


class StoreResource(ResponseModel):
    resource_id: UUID
    owner_project: str
    name: str
    provider: str
    state: str
    observed_state: str
    version: int
    quota_bytes: int
    extensions: list[str]
    created_at: datetime
    updated_at: datetime


class StoreGrant(ResponseModel):
    grant_id: UUID
    resource_id: UUID
    kind: Literal["human", "binding"]
    state: str
    observed_state: str
    version: int
    mode: Literal["read-only", "read-write"]


class StoreCredential(ResponseModel):
    credential_id: UUID
    grant_id: UUID
    state: str
    expires_at: datetime


def envelope(title, **fields):
    """Declare an extensible response with required, typed top-level fields."""
    return create_model(
        title,
        __base__=ResponseModel,
        **{key: (value, ...) for key, value in fields.items()},
    )


Status = envelope("Status", status=str)
CredentialStatus = envelope("CredentialStatus", credential_id=str, status=str)
ProjectGrants = envelope("ProjectGrants", project=str, grants=list[Object])
GrantList = envelope("GrantList", grants=list[Object])
CredentialList = envelope("CredentialList", credentials=list[Object])
ProjectCredentialList = envelope(
    "ProjectCredentialList", project=str, credentials=list[Object]
)
IssuedCredential = envelope(
    "IssuedCredential",
    credential_id=str,
    client_id=str,
    client_secret=str,
    token_endpoint=str,
)
ProjectObservation = envelope("ProjectObservation", project=str, state=str)
Page = envelope("Page", items=list[Object], next_cursor=str | None)
AccessList = envelope("AccessList", items=list[AccessResource])
StoreList = envelope("StoreList", resources=list[StoreResource])
StoreGrantList = envelope("StoreGrantList", grants=list[StoreGrant])
StoreBindingList = envelope("StoreBindingList", bindings=list[StoreGrant])
StoreCredentialList = envelope("StoreCredentialList", credentials=list[StoreCredential])
Configuration = envelope(
    "ConfigurationState",
    project=str,
    revision=int,
    values=dict[str, str],
    activation=Object,
)
SecretList = envelope(
    "SecretList", project=str, secrets=list[Object], activation=Object
)
RevisionList = envelope(
    "RevisionList", project=str, current_revision=int | None, revisions=list[Object]
)
ProjectPolicy = envelope("ProjectPolicy", project=str, classification=str | None)
ProjectContext = envelope(
    "ProjectContext",
    project=str,
    classification=str | None,
    external_model_eligible=bool,
    current_revision=int | None,
    permissions=dict[str, bool],
)
AIRun = envelope(
    "AIRun", run_id=str, project=str, kind=str, state=str, result=JsonValue
)
Proposal = envelope(
    "Proposal", proposal_id=str, diff=JsonValue, diff_sha256=str, rollback_plan=Object
)
RecoveryRequests = envelope("RecoveryRequests", requests=list[Object])
LifecyclePreview = envelope(
    "LifecyclePreview",
    project=str,
    project_id=UUID,
    status=str,
    action=str,
    inventory=Object,
    blockers=list[str],
    scope_token=str,
    expires_in_seconds=int,
)

MAIN = {
    "health": Status,
    "ready": Status,
    "projects": list[ProjectSummary],
    "create_empty_project": ProjectSummary,
    "capabilities": envelope(
        "Capabilities",
        apiVersion=str,
        apiVersions=list[str],
        environments=Object,
        imageRegistries=list[str],
        hostedApplicationAccess=Object,
        observability=Object,
    ),
    "create_deployment_credential": IssuedCredential,
    "rotate_deployment_credential": IssuedCredential,
    "create_test_runner_credential": IssuedCredential,
    "rotate_test_runner_credential": IssuedCredential,
    "create_test_identity": IssuedCredential,
    "list_deployment_credentials": ProjectCredentialList,
    "list_test_runner_credentials": CredentialList,
    "list_test_identities": CredentialList,
    "revoke_deployment_credential": CredentialStatus,
    "revoke_test_runner_credential": CredentialStatus,
    "revoke_test_identity": CredentialStatus,
    "test_context": envelope("TestContext", kind=str),
    "inspect_project_permissions": ProjectGrants,
    "inspect_project_security_configuration": envelope(
        "ProjectSecurity",
        project=str,
        namespace=Object,
        resource_quota=Object,
        limit_range=Object,
        network_policy=Object,
        workload_security=Object,
    ),
    "export_audit_events": envelope(
        "AuditExport", start=str, end=str, events=list[Object]
    ),
    "provision": OperationAccepted,
    "rollback": OperationAccepted,
    "restart": OperationAccepted,
    "put_configuration": OperationAccepted,
    "operation_status": DeploymentOperation | AccessOperation | LifecycleOperation,
    "drift": ProjectObservation,
    "project_application_metrics": ProjectObservation,
    "resource_usage": ProjectObservation,
    "resource_inventory": ProjectObservation,
    "project_logs": ProjectObservation,
    "retained_project_logs": ProjectObservation,
    "project_trace": envelope(
        "ProjectTrace", project=str, trace_id=str, spans=list[Object]
    ),
    "set_ai_policy": ProjectPolicy,
    "get_ai_policy": ProjectPolicy,
    "ai_context": ProjectContext,
    "list_ai_runs": Page,
    "list_ai_proposals": Page,
    "create_ai_run": envelope(
        "AIRunAccepted", run_id=str, project=str, state=str, result=JsonValue
    ),
    "get_ai_run": AIRun,
    "create_ai_proposal": Proposal,
    "get_ai_proposal": envelope("AIProposalDetail", proposal_id=str, state=str),
    "approve_ai_proposal": envelope("AIProposalApproval", proposal_id=str, state=str),
    "execute_ai_proposal": envelope(
        "AIProposalExecution",
        proposal_id=str,
        operation_id=str,
        state=str,
        revision=int,
        operation_status_url=str,
    ),
    "component_status": envelope(
        "ComponentStatus", project=str, revision=int, components=list[Object]
    ),
    "get_configuration": Configuration,
    "list_secrets": SecretList,
    "set_secret": envelope(
        "SecretChange",
        name=str,
        rotated=bool,
        rollout_required=bool,
        rollout_started=bool,
    ),
    "delete_secret": envelope(
        "SecretRemoval", name=str, rollout_required=bool, rollout_started=bool
    ),
    "confirm_secret_rotation": envelope(
        "SecretConfirmation", name=str, version=int, state=str
    ),
    "revert_secret_rotation": envelope(
        "SecretRevert", name=str, rollout_required=bool, rollout_started=bool
    ),
    "revisions": RevisionList,
    "data_services": envelope(
        "DataServices",
        project=str,
        services=list[Object],
        bindings=list[Object],
        latest_recovery_request=Object | None,
    ),
    "request_data_service_recovery": envelope(
        "RecoveryRequest", project=str, request_id=str, status=str
    ),
    "review_data_service_recovery_request": envelope(
        "RecoveryReview", project=str, request_id=str, status=str
    ),
    "list_data_service_recovery_requests": RecoveryRequests,
    "operator_capacity": envelope("Capacity", state=str, admission=Object),
    "inspect_retirement": envelope(
        "RetirementState",
        project=str,
        status=str,
        retired_at=str | None,
        retained=JsonValue,
        credential_cleanup=dict[str, int],
    ),
    "get_project_grants": ProjectGrants,
    "get_platform_grants": GrantList,
    "put_project_grant": envelope(
        "ProjectGrant", project=str, issuer=str, subject=str, role=str
    ),
    "delete_project_grant": envelope(
        "ProjectGrantRevoked", project=str, issuer=str, subject=str, revoked=bool
    ),
    "put_platform_grant": envelope("PlatformGrant", issuer=str, subject=str, role=str),
    "delete_platform_grant": envelope(
        "PlatformGrantRevoked", issuer=str, subject=str, revoked=bool
    ),
}


def model_for(endpoint):
    module, name = endpoint.__module__, endpoint.__name__
    if module.endswith(".main"):
        return MAIN.get(name)
    if module.endswith(".access_api"):
        if name in {
            "list_groups",
            "revisions",
            "requests",
            "list_memberships",
            "service_requests",
        }:
            return AccessList
        if name == "access_operations":
            return envelope("AccessOperationSummaries", items=list[Object], limit=int)
        if name == "access_context":
            return envelope(
                "ApplicationAccessContext",
                project=str,
                permissions=dict[str, bool],
                eligible=bool,
            )
        if name == "recover":
            return envelope(
                "AccessRecovery",
                operationIds=list[str],
                browserSessionsInvalidated=bool,
            )
        return AccessResource
    if module.endswith(".stores.api"):
        return {
            "context": envelope(
                "StoreContext",
                project=str,
                manage=bool,
                platform_admin=bool,
                providers=list[Object],
                limits=Object,
            ),
            "list_resources": StoreList,
            "create_resource": StoreResource,
            "get_resource": StoreResource,
            "rename_resource": StoreResource,
            "set_quota": StoreResource,
            "retire_resource": StoreResource,
            "purge_resource": StoreResource,
            "purge_preview": envelope(
                "StorePurgePreview", resource_id=str, owner_project=str, version=int
            ),
            "list_grants": StoreGrantList,
            "create_human_grant": StoreGrant,
            "request_binding": StoreGrant,
            "list_bindings": StoreBindingList,
            "approve_binding": StoreGrant,
            "change_mode": StoreGrant,
            "revoke_grant": StoreGrant,
            "replace_key": envelope("HumanKey", fingerprint=str),
            "my_resources": envelope(
                "HumanStoreAccess", key_fingerprint=str | None, grants=list[Object]
            ),
            "list_own_credentials": StoreCredentialList,
            "issue_credential": StoreCredential,
            "get_credential": StoreCredential,
            "launch_console": envelope("StoreConsole", url=str),
        }.get(name)
    if module.endswith(".lifecycle.api") and name.endswith("preview"):
        return LifecyclePreview
    return None
