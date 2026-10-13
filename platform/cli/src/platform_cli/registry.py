"""Explicit domain commands for every public administration API operation.

The registry drives command construction and contract coverage. Paths are public
API paths, never provider paths. Policy stays on the server.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    command: str
    method: str
    path: str
    description: str
    body: str | None = None
    fields: tuple[str, ...] = ()
    query: tuple[str, ...] = ()
    version: str | None = None
    idempotent: bool = False
    family: str | None = None
    destructive: bool = False
    credential: bool = False
    access_resource: bool = False


COMMANDS: list[CommandSpec] = []


def add(command, method, path, description, **kwargs):
    COMMANDS.append(CommandSpec(command, method, path, description, **kwargs))


P = "/projects/{name}"
A = "/v1/projects/{project}"
add("capabilities get", "GET", "/v1/capabilities", "Discover supported capabilities.")
add("projects list", "GET", "/projects", "List authorized projects.")
add("projects create", "POST", "/projects", "Create an empty project (requires platform authority).", body="project", fields=("project",))
add("deploy apply", "PUT", P, "Apply a complete application declaration.", body="file", family="deployment")
for command, suffix, description in (
    ("components list", "components", "Inspect component status."),
    ("resources", "resources", "Inspect resource inventory."),
    ("usage", "resource-usage", "Inspect usage and resource limits."),
    ("drift", "drift", "Inspect desired and observed drift."),
    ("revisions list", "revisions", "List retained deployment revisions."),
    ("config get", "configuration", "Read configuration and activation state."),
    ("secrets list", "secrets", "List secret metadata, never values."),
    ("data-services list", "data-services", "Inspect managed data services."),
    ("retirement preview", "retirement-preview", "Preview retirement and its pinned scope."),
    ("grants list", "grants", "List project role grants."),
    ("credentials list", "deployment-credentials", "List CI credential metadata."),
):
    add(command, "GET", P + "/" + suffix, description)
LOG_FILTERS = ("tail", "since", "component", "instance", "after", "before")
add("logs", "GET", P + "/logs", "Read or follow bounded current logs.", query=LOG_FILTERS + ("search",))
add("logs retained", "GET", P + "/retained-logs", "Read retained operational log envelopes.", query=LOG_FILTERS)
add("operations get", "GET", "/v1/operations/{operation_id}", "Inspect a deployment operation.", family="deployment")
add("config replace", "PUT", P + "/configuration", "Replace configuration from a complete JSON document.", body="file", version="deployment", family="deployment")
add("restart", "POST", P + "/restart", "Restart application workloads.", family="deployment", destructive=True)
add("rollback", "POST", P + "/rollback", "Restore a retained deployment revision.", body="revision", fields=("revision",), family="deployment", destructive=True)
add("data-services recovery request", "POST", P + "/data-services/recovery-requests", "Request operator assistance for a data service.", body="file", fields=("reason",))
add("retirement apply", "POST", P + "/retire", "Retire a project using a pinned preview scope.", body="retirement", fields=("scope_token",), destructive=True)
add("secrets set", "PUT", P + "/secrets/{secret}", "Create or rotate a write-only secret.", body="secret")
for action, method in (("delete", "DELETE"), ("confirm", "POST"), ("revert", "POST")):
    suffix = "" if action == "delete" else "/" + action
    add("secrets " + action, method, P + "/secrets/{secret}" + suffix, "Manage secret " + action + ".", destructive=True)
for action, method in (("set", "PUT"), ("delete", "DELETE")):
    add("grants " + action, method, P + "/grants", "Manage a project role grant.", body="grant", fields=("issuer", "subject", "role", "display_name") if action == "set" else ("issuer", "subject"), destructive=action == "delete")
add("credentials create", "POST", P + "/deployment-credentials", "Create a CI credential; return its secret once.", body="credential", fields=("name", "expires_in_days"), credential=True)
add("credentials rotate", "POST", P + "/deployment-credentials/{credential_id}/rotate", "Rotate a CI credential with bounded overlap.", body="credential", fields=("expires_in_days", "overlap_hours"), credential=True)
add("credentials revoke", "DELETE", P + "/deployment-credentials/{credential_id}", "Revoke a CI credential.", destructive=True)

for command, suffix, description, query, resource in (
    ("access context", "application-access-context", "Inspect access eligibility and permissions.", (), False),
    ("access operations list", "application-access-operations", "List authorized access operations.", (), False),
    ("access groups list", "application-groups", "List application groups.", (), True),
    ("access human-requests list", "application-access-requests", "List first-login requests.", ("state",), True),
    ("access memberships list", "application-group-memberships", "List application group memberships.", (), True),
    ("access services list", "service-access-requests", "List incoming and outgoing service requests.", (), True),
    ("governance get", "governance", "Read classification and retention governance.", (), True),
):
    add(command, "GET", A + "/" + suffix, description, query=query, access_resource=resource)
add("access groups create", "POST", A + "/application-groups", "Create an application group.", body="group", fields=("name", "display_name"), idempotent=True, access_resource=True)
add("access groups delete", "DELETE", A + "/application-groups/{resource_id}", "Delete an unreferenced application group.", version="required", destructive=True, family="access", access_resource=True)
POLICY = A + "/applications/{application}/access-policy"
add("access policy get", "GET", POLICY, "Read the active route access policy.", access_resource=True)
add("access policy apply", "PUT", POLICY, "Apply a complete route policy.", body="file", version="optional", family="access", access_resource=True)
add("access policy revisions", "GET", POLICY + "/revisions", "List immutable policy revisions.", access_resource=True)
add("access policy rollback", "POST", POLICY + "/rollback", "Restore the previous policy revision.", version="required", family="access", destructive=True, access_resource=True)
add("governance replace", "PUT", A + "/governance", "Replace project governance from JSON.", body="file", version="optional", access_resource=True)
for action in ("approve", "reject", "reopen", "cancel", "assign-groups"):
    suffix = "groups" if action == "assign-groups" else action
    grouping = action in {"approve", "assign-groups"}
    add("access human-requests " + action, "POST", A + "/application-access-requests/{resource_id}/" + suffix,
        "Manage a first-login request.", body="groups" if grouping else None,
        fields=("group",) if grouping else (), version="required", family="access",
        destructive=action in {"reject", "cancel"}, access_resource=True)
add("access memberships revoke", "DELETE", A + "/application-group-memberships/{resource_id}", "Revoke an application group membership.", version="required", family="access", destructive=True, access_resource=True)
SERVICES = A + "/service-access-requests"
add("access services request", "POST", SERVICES, "Request project-wide access to an application's public service.", body="service", fields=("name", "provider_project", "application", "project_wide_credential"), idempotent=True, access_resource=True)
for action, method in (("approve", "POST"), ("reject", "POST"), ("cancel", "POST"), ("rotate", "POST"), ("confirm", "POST"), ("revoke", "DELETE")):
    suffix = "" if action == "revoke" else "/" + action
    body = "groups" if action == "approve" else "rotation" if action == "rotate" else None
    fields = ("group",) if body == "groups" else ("emergency",) if body == "rotation" else ()
    add("access services " + action, method, SERVICES + "/{resource_id}" + suffix, "Manage service access " + action + ".",
        body=body, fields=fields, version="required", family="access", access_resource=True,
        destructive=action in {"reject", "cancel", "confirm", "revoke", "rotate"})
add("access operations get", "GET", "/v1/access-operations/{operation_id}", "Inspect an access reconciliation operation.", family="access")
add("access operations retry", "POST", "/v1/access-operations/{operation_id}/retry", "Retry a failed operation using its resource ETag.", version="required", family="access", access_resource=True)

for command, path in (
    ("operator capacity", "/operator/capacity"),
    ("operator permissions", "/operator/projects/{name}/permissions"),
    ("operator security-configuration", "/operator/projects/{name}/security-configuration"),
    ("operator retirement", "/operator/projects/{name}/retirement"),
    ("operator purge preview", "/operator/projects/{name}/purge-preview"),
    ("operator recovery-requests list", "/operator/data-service-recovery-requests"),
    ("operator grants list", "/platform/grants"),
    ("operator test-identities list", "/platform/test-identities"),
    ("operator test-runner-credentials list", "/platform/test-runner-credentials"),
):
    add(command, "GET", path, "Inspect privileged platform administration state.", query=("test_run_id",) if command == "operator test-identities list" else ())
add("operator audit export", "GET", "/operator/audit/events", "Export redacted audit events.", query=("start", "end", "format", "limit"))
add("operator recovery-requests review", "PATCH", "/operator/data-service-recovery-requests/{request_id}", "Acknowledge or resolve a recovery request.", body="file", fields=("status",))
add("operator application-access recover", "POST", "/operator/application-access/recover", "Reconcile restored access state; invalidate sessions and uncertain credentials.", destructive=True)
add("operator purge apply", "POST", "/operator/projects/{name}/purge", "Permanently purge a retired project using its preview scope.", body="retirement", fields=("scope_token",), destructive=True)
for action, method in (("set", "PUT"), ("delete", "DELETE")):
    add("operator grants " + action, method, "/platform/grants", "Manage platform administrator grants.", body="grant", fields=("issuer", "subject", "role", "display_name") if action == "set" else ("issuer", "subject"), destructive=True)
for family, collection, fields in (
    ("test-identities", "/platform/test-identities", ("name", "role", "test_run_id", "project", "expires_in_hours")),
    ("test-runner-credentials", "/platform/test-runner-credentials", ("name", "expires_in_days")),
):
    add("operator " + family + " create", "POST", collection, "Create an explicitly privileged test automation identity.", body="credential", fields=fields, credential=True, destructive=True)
    add("operator " + family + " revoke", "DELETE", collection + "/{credential_id}", "Revoke a test automation identity.", destructive=True)
add("operator test-runner-credentials rotate", "POST", "/platform/test-runner-credentials/{credential_id}/rotate", "Rotate a test runner credential.", body="credential", fields=("expires_in_days", "overlap_hours"), credential=True, destructive=True)

EXCLUSIONS = {("GET", "/healthz"): "Service liveness probe", ("GET", "/readyz"): "Service readiness probe"}
