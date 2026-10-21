"""Opt-in lab outage drill for reclaiming a bound application operation.

Requires an otherwise idle k3d lab. It pauses the Kubernetes server, kills the
Platform API during a running apply, and restores both services in all normal
error paths. A host kill or power loss still needs operator recovery.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from uuid import UUID

from .harness import (
    API,
    DrillError,
    Keycloak,
    ROOT,
    operator_tokens,
    origin,
    require,
    settings,
    utc,
    wait_for,
)
from .human_database import IMAGE, RUN_ID, wait_deployment
from .data_preservation import project_row, visit, web_postgres_declaration

SERVER = "k3d-workloads-server-0"
OUTAGE_CONFIRMATION = "pause-" + SERVER + "-and-kill-platform-api"
CHECKS = (
    "initial-write",
    "operation-interrupted",
    "single-revision-after-retry",
    "data-survives-recovery",
    "named-resource-unchanged",
)


def project_name(run_id):
    require(bool(RUN_ID.fullmatch(run_id)), "invalid_run_id")
    return "ip-" + run_id


def declaration(project, image, run_id, binding_id, cpu_limit):
    require(project == project_name(run_id), "invalid_fixture_project")
    return web_postgres_declaration(project, image, run_id, binding_id, cpu_limit)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("plan", "run"))
    result.add_argument("--api", default="http://127.0.0.1:8000")
    result.add_argument("--run-id", required=True)
    result.add_argument(
        "--fixture-image",
        required=True,
        help="digest-pinned examples/web-postgres image",
    )
    result.add_argument("--confirm-environment")
    result.add_argument("--confirm-outage")
    result.add_argument("--operator-token-file", type=Path)
    result.add_argument("--settings", type=Path, default=ROOT / ".env")
    result.add_argument("--kubectl", type=Path, default=ROOT / ".runtime/bin/kubectl")
    result.add_argument(
        "--kubeconfig", type=Path, default=ROOT / ".runtime/admin.kubeconfig"
    )
    return result


def validate(args):
    args.api = origin(args.api)
    project_name(args.run_id)
    require(
        bool(IMAGE.fullmatch(args.fixture_image)),
        "digest_pinned_fixture_image_required",
    )
    if args.command == "run":
        require(args.api == "http://127.0.0.1:8000", "local_api_required")
        require(
            args.confirm_environment == args.api,
            "explicit_environment_confirmation_required",
        )
        require(
            args.confirm_outage == OUTAGE_CONFIRMATION,
            "explicit_outage_confirmation_required",
        )
        require(args.operator_token_file is not None, "operator_token_file_required")


class Report:
    def __init__(self, run_id, api, image):
        parent = ROOT / ".runtime/interrupted-provisioning"
        require(not parent.is_symlink(), "unsafe_report_parent")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(
            stat.S_IMODE(parent.stat().st_mode) & 0o077 == 0,
            "unsafe_report_parent_permissions",
        )
        self.directory = parent / run_id
        require(
            not self.directory.exists() and not self.directory.is_symlink(),
            "run_directory_exists",
        )
        self.directory.mkdir(mode=0o700)
        self.data = {
            "format": 1,
            "runId": run_id,
            "api": api,
            "fixtureImage": image,
            "project": project_name(run_id),
            "startedAt": utc(),
            "result": "running",
            "projectCreateAttempted": False,
            "projectCreated": False,
            "resourceId": None,
            "bindingId": None,
            "revision": None,
            "checks": [],
            "outage": "not-started",
            "cleanup": "pending",
            "databaseRetained": True,
        }
        self.save()

    def save(self):
        path = self.directory / "report.json"
        require(not path.is_symlink(), "unsafe_report_file")
        temporary = self.directory / (".report." + os.urandom(8).hex())
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(self.data, output, indent=2)
            output.write("\n")
        os.replace(temporary, path)

    def check(self, name, passed):
        require(name in CHECKS and isinstance(passed, bool), "unsafe_evidence")
        self.data["checks"].append(
            {"name": name, "result": "passed" if passed else "failed", "at": utc()}
        )
        self.save()
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        require(passed, name)


def command(args, *, timeout=30):
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, cwd=ROOT
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DrillError("host_command_failed") from None
    require(result.returncode == 0, "host_command_failed")
    return result.stdout.strip()


def sql_scalar(query):
    return command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-X",
            "-U",
            "postgres",
            "-d",
            "platform",
            "-tAc",
            query,
        ]
    )


def operation_state(operation_id):
    identifier = str(UUID(operation_id))
    return sql_scalar(
        "SELECT state FROM application_operations WHERE operation_id='"
        + identifier
        + "'"
    )


def named_database_exists(resource_id):
    identifier = str(UUID(resource_id))
    database = "resource_" + identifier.replace("-", "")
    database_count = sql_scalar(
        "SELECT COUNT(*) FROM pg_database WHERE datname='" + database + "'"
    )
    role_count = sql_scalar(
        "SELECT COUNT(*) FROM pg_roles WHERE rolname='" + database + "'"
    )
    return database_count == "1" and role_count == "1"


def revision_outcomes(project, revision):
    require(
        re.fullmatch(r"ip-[0-9a-f]{12}", project)
        and isinstance(revision, int)
        and revision > 0,
        "invalid_operation_scope",
    )
    query = (
        "SELECT COALESCE(string_agg(o.state, ',' ORDER BY o.created_at), '') "
        "FROM projects p JOIN project_environments e ON e.project_id=p.project_id "
        "JOIN project_applications a ON a.environment_id=e.environment_id "
        "JOIN application_operations o ON o.application_id=a.application_id "
        "WHERE p.name='" + project + "' AND o.revision=" + str(revision)
    )
    return sql_scalar(query).split(",")


def host_preflight(config, api, report, args):
    require(
        config.get("CAPACITY_ADMISSION_ENABLED", "false").lower() != "true",
        "capacity_admission_must_be_disabled",
    )
    require(
        args.kubectl.is_file() and os.access(args.kubectl, os.X_OK), "kubectl_missing"
    )
    require(
        args.kubeconfig.is_file() and not args.kubeconfig.is_symlink(),
        "kubeconfig_missing",
    )
    api.request("GET", "/platform/test-context")
    projects = api.request("GET", "/projects")
    require(
        all(row["status"] in ("empty", "retired") for row in projects),
        "active_projects_in_lab",
    )
    require(project_row(api, report.data["project"]) is None, "run_project_name_in_use")
    require(
        command(["docker", "inspect", "--format", "{{.State.Paused}}", SERVER])
        == "false",
        "k3d_server_already_paused",
    )
    require(
        bool(command(["docker", "compose", "ps", "-q", "platform-api"])),
        "platform_api_not_running",
    )


def deploy_initial(args, api, report):
    project = report.data["project"]
    report.data["projectCreateAttempted"] = True
    report.save()
    api.request("POST", "/projects", {"name": project}, statuses=(201,))
    report.data["projectCreated"] = True
    report.save()
    resource = api.request(
        "POST",
        "/v1/projects/" + project + "/resources",
        {"name": "state", "provider": "postgresql"},
        statuses=(202,),
    )
    resource_id = resource["resource_id"]
    report.data["resourceId"] = resource_id
    report.save()
    wait_for(
        lambda: (
            api.request("GET", "/v1/resources/" + resource_id)["observed_state"]
            == "active"
        ),
        "named_database_not_ready",
    )
    binding = api.request(
        "POST",
        "/v1/projects/" + project + "/resource-bindings",
        {"resource_id": resource_id, "component": "web", "mode": "read-write"},
        statuses=(202,),
    )
    binding_id = binding["grant_id"]
    report.data["bindingId"] = binding_id
    report.save()
    wait_for(
        lambda: any(
            row["grant_id"] == binding_id and row["observed_state"] == "active"
            for row in api.request(
                "GET", "/v1/projects/" + project + "/resource-bindings"
            )["bindings"]
        ),
        "named_binding_not_ready",
    )
    accepted = api.request(
        "PUT",
        "/projects/" + project,
        declaration(project, args.fixture_image, args.run_id, binding_id, "500m"),
        etag=0,
        statuses=(202,),
    )
    wait_deployment(api, accepted)
    report.check("initial-write", visit(args.kubectl, args.kubeconfig, project) == 1)
    return accepted["revision"]


def restore_host(report):
    # Both commands run even if either one fails. Never leave the cluster paused
    # merely because restarting the API failed (or vice versa).
    restored = True
    for args in (
        ["docker", "unpause", SERVER],
        ["docker", "compose", "up", "-d", "platform-api"],
    ):
        try:
            command(args, timeout=90)
        except DrillError:
            restored = False
    report.data["outage"] = (
        "restored" if restored else "restore-failed-manual-action-required"
    )
    report.save()
    require(restored, "host_restore_failed")


def interrupt(args, api, report, initial_revision):
    project = report.data["project"]
    spec = declaration(
        project, args.fixture_image, args.run_id, report.data["bindingId"], "600m"
    )
    pause_attempted = False
    try:
        pause_attempted = True
        command(["docker", "pause", SERVER])
        report.data["outage"] = "cluster-paused"
        report.save()
        accepted = api.request(
            "PUT", "/projects/" + project, spec, etag=initial_revision, statuses=(202,)
        )
        require(accepted["revision"] == initial_revision + 1, "unexpected_revision")
        report.data["revision"] = accepted["revision"]
        report.save()
        wait_for(
            lambda: operation_state(accepted["operation_id"]) == "running",
            "operation_not_running_before_kill",
            60,
        )
        command(["docker", "compose", "kill", "platform-api"])
        report.data["outage"] = "api-killed"
        report.save()
        report.check(
            "operation-interrupted",
            operation_state(accepted["operation_id"]) == "running",
        )
    finally:
        if pause_attempted:
            restore_host(report)
    return accepted, spec


def api_ready(api):
    try:
        return api.request("GET", "/readyz").get("status") == "ready"
    except Exception:
        return False


def run(args, config, api, report):
    host_preflight(config, api, report, args)
    first_revision = deploy_initial(args, api, report)
    accepted, spec = interrupt(args, api, report, first_revision)
    wait_for(lambda: api_ready(api), "api_not_ready_after_restart", 120)
    repeated = api.request(
        "PUT",
        "/projects/" + report.data["project"],
        spec,
        etag=accepted["revision"],
        statuses=(202,),
    )
    require(repeated["revision"] == accepted["revision"], "retry_created_revision")
    wait_deployment(api, accepted)
    wait_deployment(api, repeated)
    revisions = api.request("GET", "/projects/" + report.data["project"] + "/revisions")
    outcomes = revision_outcomes(report.data["project"], accepted["revision"])
    report.check(
        "single-revision-after-retry",
        revisions["current_revision"] == accepted["revision"]
        and [row["revision"] for row in revisions["revisions"]]
        == [accepted["revision"], first_revision]
        and 1 <= len(outcomes) <= 2
        and all(state == "succeeded" for state in outcomes),
    )
    report.check(
        "data-survives-recovery",
        visit(args.kubectl, args.kubeconfig, report.data["project"]) == 2,
    )
    resource = api.request("GET", "/v1/resources/" + report.data["resourceId"])
    resources = api.request(
        "GET", "/v1/projects/" + report.data["project"] + "/resources"
    )["resources"]
    bindings = api.request(
        "GET", "/v1/projects/" + report.data["project"] + "/resource-bindings"
    )["bindings"]
    report.check(
        "named-resource-unchanged",
        resource["observed_state"] == "active"
        and named_database_exists(report.data["resourceId"])
        and len(resources) == 1
        and resources[0]["resource_id"] == report.data["resourceId"]
        and len(bindings) == 1
        and bindings[0]["grant_id"] == report.data["bindingId"]
        and bindings[0]["observed_state"] == "active",
    )


def retire(api, report):
    if not report.data["projectCreateAttempted"]:
        report.data["cleanup"] = "not-needed"
        report.save()
        return
    if not report.data["projectCreated"]:
        report.data["cleanup"] = "incomplete-retry-required"
        report.save()
        return
    project = report.data["project"]
    row = project_row(api, project)
    require(row is not None, "cleanup_project_missing")
    if row["status"] != "retired":
        spec = row.get("spec")
        require(
            spec is None
            or (spec.get("configuration") or {}).get("ACCEPTANCE_RUN_ID")
            == report.data["runId"],
            "cleanup_project_changed",
        )
        preview = api.request("GET", "/projects/" + project + "/retirement-preview")
        require(not preview["blockers"], "cleanup_retirement_blocked")
        confirmation = {"confirm_name": project, "scope_token": preview["scope_token"]}
        wait_for(
            lambda: (
                api.request(
                    "POST",
                    "/projects/" + project + "/retire",
                    confirmation,
                    statuses=(200, 202),
                ).get("status")
                == "retired"
            ),
            "fixture_retirement",
            180,
        )
    report.data["cleanup"] = "retired-data-retained"
    report.save()


def main(argv=None):
    report = None
    try:
        args = parser().parse_args(argv)
        validate(args)
        if args.command == "plan":
            print(
                json.dumps(
                    {
                        "format": 1,
                        "runId": args.run_id,
                        "mutates": False,
                        "project": project_name(args.run_id),
                        "fixtureImage": args.fixture_image,
                        "outage": [
                            "pause " + SERVER,
                            "kill platform-api",
                            "unpause " + SERVER,
                            "start platform-api",
                        ],
                        "checks": list(CHECKS),
                        "databaseRetained": True,
                        "requiresIdleLab": True,
                        "requiresCapacityAdmissionDisabled": True,
                    },
                    indent=2,
                )
            )
            return 0
        config = settings(args.settings)
        api = API(args.api, operator_tokens(args.operator_token_file, Keycloak(config)))
        report = Report(args.run_id, args.api, args.fixture_image)
        error = None
        try:
            run(args, config, api, report)
        except (Exception, KeyboardInterrupt) as exc:
            error = (
                str(exc)
                if isinstance(exc, DrillError)
                else (
                    "interrupted"
                    if isinstance(exc, KeyboardInterrupt)
                    else "dependency_failure"
                )
            )
        # If recovery of the shared services failed, avoid API cleanup attempts.
        if report.data["outage"] != "restore-failed-manual-action-required":
            try:
                retire(api, report)
            except (Exception, KeyboardInterrupt):
                report.data["cleanup"] = "incomplete-retry-required"
                report.save()
        else:
            report.data["cleanup"] = "incomplete-retry-required"
        report.data.update(
            result="failed"
            if error or report.data["cleanup"] == "incomplete-retry-required"
            else "passed",
            finishedAt=utc(),
        )
        if error:
            report.data["errorCode"] = error
        report.save()
        print("REPORT " + str(report.directory / "report.json"), flush=True)
        return 0 if report.data["result"] == "passed" else 1
    except (Exception, KeyboardInterrupt) as exc:
        code = (
            str(exc)
            if isinstance(exc, DrillError)
            else (
                "interrupted"
                if isinstance(exc, KeyboardInterrupt)
                else "configuration_or_dependency_failure"
            )
        )
        if report is not None:
            report.data.update(result="failed", finishedAt=utc(), errorCode=code)
            report.save()
        print("ERROR " + code, flush=True)
        return 1
