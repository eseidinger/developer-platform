"""Opt-in named PostgreSQL preservation acceptance using examples/web-postgres."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
from uuid import UUID

from .harness import API, DrillError, Keycloak, ROOT, operator_tokens, origin, require, settings, utc, wait_for
from .human_database import IMAGE, RUN_ID, wait_deployment

CHECKS = ("initial-write", "redeploy-preserves-data", "restart-preserves-data", "rollback-preserves-data")
VISIT = ("import json,urllib.request; "
         "print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/visits',timeout=10))['visits'])")


def project_name(run_id):
    require(bool(RUN_ID.fullmatch(run_id)), "invalid_run_id")
    return "dp-" + run_id


def declaration(project, image, run_id, binding_id, cpu_limit):
    require(project == project_name(run_id) and bool(IMAGE.fullmatch(image)), "invalid_fixture_declaration")
    require(cpu_limit in ("500m", "600m"), "invalid_fixture_cpu_limit")
    try:
        UUID(binding_id)
    except ValueError:
        raise DrillError("invalid_binding_id") from None
    return {"apiVersion": "platform.example/v1alpha2", "kind": "Application",
        "metadata": {"name": project, "project": project}, "spec": {
            "components": [{"name": "web", "type": "service", "runtime": {"type": "container", "image": image},
                "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                "replicas": 1, "exposure": "private", "bindings": [{"bindingId": binding_id, "envPrefix": ""}],
                "health": {"readiness": {"path": "/health/ready"}},
                "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                              "limits": {"cpu": cpu_limit, "memory": "256Mi"}}}],
            "configuration": {"values": {"DEMO_FAIL_READY": "false", "ACCEPTANCE_RUN_ID": run_id}}}}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("plan", "run"))
    result.add_argument("--api", default="http://127.0.0.1:8000")
    result.add_argument("--run-id", required=True)
    result.add_argument("--fixture-image", required=True, help="digest-pinned examples/web-postgres image")
    result.add_argument("--confirm-environment")
    result.add_argument("--operator-token-file", type=Path)
    result.add_argument("--settings", type=Path, default=ROOT / ".env")
    result.add_argument("--kubectl", type=Path, default=ROOT / ".runtime/bin/kubectl")
    result.add_argument("--kubeconfig", type=Path, default=ROOT / ".runtime/admin.kubeconfig")
    return result


def validate(args):
    args.api = origin(args.api)
    project_name(args.run_id)
    require(bool(IMAGE.fullmatch(args.fixture_image)), "digest_pinned_fixture_image_required")
    if args.command == "run":
        require(args.confirm_environment == args.api, "explicit_environment_confirmation_required")
        require(args.operator_token_file is not None, "operator_token_file_required")


class Report:
    def __init__(self, run_id, api, image):
        parent = ROOT / ".runtime/data-preservation"
        require(not parent.is_symlink(), "unsafe_report_parent")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(stat.S_IMODE(parent.stat().st_mode) & 0o077 == 0, "unsafe_report_parent_permissions")
        self.directory = parent / run_id
        require(not self.directory.exists() and not self.directory.is_symlink(), "run_directory_exists")
        self.directory.mkdir(mode=0o700)
        self.data = {"format": 1, "runId": run_id, "api": api, "fixtureImage": image,
            "project": project_name(run_id), "startedAt": utc(), "result": "running",
            "projectCreateAttempted": False, "projectCreated": False,
            "resourceId": None, "bindingId": None,
            "checks": [], "cleanup": "pending", "databaseRetained": True}
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

    def check(self, name, passed, visits):
        require(name in CHECKS and isinstance(visits, int) and visits > 0, "unsafe_evidence")
        self.data["checks"].append({"name": name, "result": "passed" if passed else "failed",
                                    "visits": visits, "at": utc()})
        self.save()
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        require(passed, name)


def visit(kubectl, kubeconfig, project):
    command = [str(kubectl), "--kubeconfig", str(kubeconfig), "-n", "project-" + project,
               "exec", "deployment/web", "--", "python", "-c", VISIT]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=35)
        require(result.returncode == 0, "fixture_visit_failed")
        count = int(result.stdout.strip())
        require(count > 0, "invalid_fixture_visit_count")
        return count
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise DrillError("fixture_visit_failed") from None


def project_row(api, project):
    return next((row for row in api.request("GET", "/projects") if row["name"] == project), None)


def retire(api, report):
    project = report.data["project"]
    if not report.data["projectCreateAttempted"]:
        report.data["cleanup"] = "not-needed"
        report.save()
        return
    # A lost create response cannot prove ownership; leave it for manual review.
    if not report.data["projectCreated"]:
        report.data["cleanup"] = "incomplete-retry-required"
        report.save()
        return
    row = project_row(api, project)
    if row is None:
        report.data["cleanup"] = "not-needed"
        report.save()
        return
    if row["status"] != "retired":
        spec = row.get("spec")
        require(spec is None or (spec.get("configuration") or {}).get("ACCEPTANCE_RUN_ID") == report.data["runId"],
                "cleanup_project_changed")
        preview = api.request("GET", "/projects/" + project + "/retirement-preview")
        require(not preview["blockers"], "cleanup_retirement_blocked")
        confirmation = {"confirm_name": project, "scope_token": preview["scope_token"]}
        wait_for(lambda: api.request("POST", "/projects/" + project + "/retire",
            confirmation, statuses=(200, 202)).get("status") == "retired", "fixture_retirement", 180)
    report.data["cleanup"] = "retired-data-retained"
    report.save()


def run(args, api, report):
    project = report.data["project"]
    require(args.kubectl.is_file() and os.access(args.kubectl, os.X_OK), "kubectl_missing")
    require(args.kubeconfig.is_file() and not args.kubeconfig.is_symlink(), "kubeconfig_missing")
    api.request("GET", "/platform/test-runner-credentials")
    require(project_row(api, project) is None, "run_project_name_in_use")
    report.data["projectCreateAttempted"] = True
    report.save()
    api.request("POST", "/projects", {"name": project}, statuses=(201,))
    report.data["projectCreated"] = True
    report.save()
    resource = api.request("POST", "/v1/projects/" + project + "/resources",
        {"name": "state", "provider": "postgresql"}, statuses=(202,))
    report.data["resourceId"] = resource["resource_id"]
    report.save()
    wait_for(lambda: api.request("GET", "/v1/resources/" + resource["resource_id"])["observed_state"] == "active",
             "named_database_not_ready")
    binding = api.request("POST", "/v1/projects/" + project + "/resource-bindings",
        {"resource_id": resource["resource_id"], "component": "web", "mode": "read-write"}, statuses=(202,))
    report.data["bindingId"] = binding["grant_id"]
    report.save()
    wait_for(lambda: any(row["grant_id"] == binding["grant_id"] and row["observed_state"] == "active"
        for row in api.request("GET", "/v1/projects/" + project + "/resource-bindings")["bindings"]),
        "named_binding_not_ready")
    path = "/projects/" + project
    first = api.request("PUT", path,
        declaration(project, args.fixture_image, args.run_id, binding["grant_id"], "500m"), etag=0, statuses=(202,))
    wait_deployment(api, first)
    initial = visit(args.kubectl, args.kubeconfig, project)
    report.check("initial-write", initial == 1, initial)
    second = api.request("PUT", path,
        declaration(project, args.fixture_image, args.run_id, binding["grant_id"], "600m"),
        etag=first["revision"], statuses=(202,))
    wait_deployment(api, second)
    after_redeploy = visit(args.kubectl, args.kubeconfig, project)
    report.check("redeploy-preserves-data", after_redeploy == initial + 1, after_redeploy)
    restarted = api.request("POST", path + "/restart", statuses=(202,))
    wait_deployment(api, restarted)
    after_restart = visit(args.kubectl, args.kubeconfig, project)
    report.check("restart-preserves-data", after_restart == after_redeploy + 1, after_restart)
    rolled_back = api.request("POST", path + "/rollback", {"revision": first["revision"]},
                              etag=second["revision"], statuses=(202,))
    wait_deployment(api, rolled_back)
    after_rollback = visit(args.kubectl, args.kubeconfig, project)
    report.check("rollback-preserves-data", after_rollback == after_restart + 1, after_rollback)


def main(argv=None):
    report = None
    try:
        args = parser().parse_args(argv)
        validate(args)
        if args.command == "plan":
            print(json.dumps({"format": 1, "runId": args.run_id, "mutates": False,
                "project": project_name(args.run_id), "fixtureImage": args.fixture_image,
                "checks": list(CHECKS), "retireAfterRun": True, "databaseRetained": True}, indent=2))
            return 0
        api = API(args.api, operator_tokens(args.operator_token_file, Keycloak(settings(args.settings))))
        report = Report(args.run_id, args.api, args.fixture_image)
        error = None
        try:
            run(args, api, report)
        except (Exception, KeyboardInterrupt) as exc:
            error = str(exc) if isinstance(exc, DrillError) else (
                "interrupted" if isinstance(exc, KeyboardInterrupt) else "dependency_failure")
        try:
            retire(api, report)
        except (Exception, KeyboardInterrupt):
            report.data["cleanup"] = "incomplete-retry-required"
            report.save()
        report.data.update(result="failed" if error or report.data["cleanup"] == "incomplete-retry-required"
                           else "passed", finishedAt=utc())
        if error:
            report.data["errorCode"] = error
        report.save()
        print("REPORT " + str(report.directory / "report.json"), flush=True)
        return 0 if report.data["result"] == "passed" else 1
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, DrillError) else (
            "interrupted" if isinstance(exc, KeyboardInterrupt) else "configuration_or_dependency_failure")
        if report is not None:
            report.data.update(result="failed", finishedAt=utc(), errorCode=code)
            report.save()
        print("ERROR " + code, flush=True)
        return 1
