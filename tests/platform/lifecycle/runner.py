"""Plan or run application lifecycle checks on a disposable legacy-compatibility project.

Run on the platform host with its kubeconfigs and Compose installation. The
full suite uses the digest-pinned neutral acceptance fixture (Python, port 8080).
Smoke mode accepts a simple HTTP fixture, such as http-echo on port 5678.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from ..harness import (
    API,
    IMAGE_PATTERN,
    ROOT,
    RUN_PATTERN,
    DrillError,
    Keycloak,
    Tokens,
    operator_tokens,
    origin,
    private_text,
    require,
    settings,
    utc,
    wait_for,
)
from ..human_database import wait_deployment

# Operational boundaries must journal failures and attempt cleanup, including
# unexpected dependency errors, without printing response bodies or credentials.


class Fixture:
    """Own one newly created project; never adopt or clean an existing project."""

    def __init__(self, args, api):
        self.args, self.api = args, api
        self.project = "lc-" + args.run_id
        self.path = "/projects/" + self.project
        self.created = False
        self.report = {
            "runId": args.run_id,
            "project": self.project,
            "startedAt": utc(),
            "result": "running",
            "checks": [],
            "cleanup": "not-needed",
            "databaseRetained": True,
        }
        self.output = ROOT / ".runtime/application-lifecycle" / args.run_id
        require(not self.output.parent.is_symlink(), "unsafe_report_parent")
        self.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(not self.output.exists(), "run_directory_exists")
        self.output.mkdir(mode=0o700)
        self.save()

    def save(self):
        temporary = self.output / (".report-" + uuid4().hex)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(self.report, output, indent=2)
            output.write("\n")
        temporary.replace(self.output / "report.json")

    def check(self, name, condition=True):
        self.report["checks"].append({"name": name, "passed": bool(condition)})
        self.save()
        require(condition, name)
        print("PASS " + name, flush=True)

    def request(self, method, suffix, body=None, **kwargs):
        return self.api.request(method, self.path + suffix, body, **kwargs)

    def command(self, arguments, *, input=None, check=True):
        result = subprocess.run(
            arguments,
            input=input,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        require(not check or result.returncode == 0, "fixture_command_failed")
        return result

    def kubectl(self, *arguments, namespace=True, **kwargs):
        command = [str(self.args.kubectl), "--kubeconfig", str(self.args.kubeconfig)]
        if namespace:
            command += ["-n", "project-" + self.project]
        return self.command(command + list(arguments), **kwargs)

    def pods(self):
        rows = json.loads(
            self.kubectl(
                "get",
                "pods",
                "-l",
                "app.kubernetes.io/name=" + self.project,
                "-o",
                "json",
            ).stdout
        )["items"]
        return sorted(row["metadata"]["uid"] for row in rows)

    def activate(self, surface):
        return wait_for(
            lambda: (
                self.request("GET", "/" + surface)["activation"]["state"] == "active"
            ),
            surface + "_activation_timeout",
        )

    def provision(self):
        self.api.request("GET", "/platform/test-context")
        rows = self.api.request("GET", "/projects")
        require(
            not any(row["name"] == self.project for row in rows),
            "fixture_project_exists",
        )
        self.report["cleanup"] = "incomplete-create-response-review-required"
        self.save()
        self.api.request("POST", "/projects", {"name": self.project}, statuses=(201,))
        self.created = True
        self.report["cleanup"] = "pending"
        self.save()
        spec = {
            "name": self.project,
            "image": self.args.fixture_image,
            "port": self.args.fixture_port,
            "probe_profile": "hello-world" if self.args.smoke else "status",
            "configuration": {
                "ACCEPTANCE_RUN_ID": self.args.run_id,
                "FIXTURE_ROLE": "lifecycle",
            },
        }
        first = self.request("PUT", "", spec, etag=0, statuses=(202,))
        second = self.request("PUT", "", spec, statuses=(202,))
        self.check("idempotent-provisioning", first["revision"] == second["revision"])
        wait_deployment(self.api, second)
        self.check("deployment-ready")

    def retire(self):
        if not self.created:
            return
        # Wait for in-flight changes even after an assertion failed, then retire
        # only the project whose successful creation this process observed.
        preview = wait_for(lambda: self.retirement_preview(), "retirement_blocked", 300)
        if preview["status"] == "retired":
            self.report["cleanup"] = "retired-data-retained"
            self.save()
            return
        confirmation = {
            "confirm_name": self.project,
            "scope_token": preview["scope_token"],
        }
        wait_for(
            lambda: (
                self.request("POST", "/retire", confirmation, statuses=(200, 202))[
                    "status"
                ]
                == "retired"
            ),
            "retirement_timeout",
            240,
        )
        self.report["cleanup"] = "retired-data-retained"
        self.save()

    def retirement_preview(self):
        preview = self.request("GET", "/retirement-preview")
        if preview["status"] == "retired":
            return preview
        return preview if not preview["blockers"] else None


def parser(smoke=False):
    result = argparse.ArgumentParser(description=__doc__)
    result.set_defaults(smoke=smoke)
    result.add_argument("command", choices=("plan", "run"))
    result.add_argument("--api", default="http://127.0.0.1:8000")
    result.add_argument("--run-id", required=True)
    result.add_argument("--fixture-image", required=True)
    result.add_argument("--fixture-port", type=int, default=5678 if smoke else 8080)
    result.add_argument("--confirm-environment")
    result.add_argument("--operator-token-file", type=Path)
    result.add_argument(
        "--other-token-file",
        type=Path,
        help="Private bearer token for a user without grants",
    )
    result.add_argument("--settings", type=Path, default=ROOT / ".env")
    result.add_argument("--kubectl", type=Path, default=ROOT / ".runtime/bin/kubectl")
    result.add_argument(
        "--kubeconfig", type=Path, default=ROOT / ".runtime/admin.kubeconfig"
    )
    result.add_argument(
        "--controller-kubeconfig",
        type=Path,
        default=ROOT / ".runtime/controller.kubeconfig",
    )
    return result


def validate(args, smoke):
    args.api = origin(args.api)
    require(bool(RUN_PATTERN.fullmatch(args.run_id)), "invalid_run_id")
    require(
        bool(IMAGE_PATTERN.fullmatch(args.fixture_image)),
        "digest_pinned_fixture_image_required",
    )
    require(1024 <= args.fixture_port <= 65535, "invalid_fixture_port")
    if args.command == "run":
        require(
            args.confirm_environment == args.api,
            "explicit_environment_confirmation_required",
        )
        require(args.operator_token_file is not None, "operator_token_file_required")
        require(
            smoke or args.other_token_file is not None, "ungranted_user_token_required"
        )


def main(argv=None, *, smoke=False):
    fixture = None
    try:
        args = parser(smoke).parse_args(argv)
        validate(args, smoke)
        if args.command == "plan":
            print(
                json.dumps(
                    {
                        "mutates": False,
                        "project": "lc-" + args.run_id,
                        "suite": "smoke" if smoke else "lifecycle",
                        "checks": ["deployment", "edge-routing"]
                        if smoke
                        else [
                            "deployment",
                            "edge-routing",
                            "configuration",
                            "secret-rotation",
                            "failed-pod-logs",
                            "authorization",
                            "audit",
                            "retirement",
                        ],
                        "cleanup": "retire-project-retain-data",
                    },
                    indent=2,
                )
            )
            return 0
        if not smoke:
            require(
                args.kubectl.is_file() and os.access(args.kubectl, os.X_OK),
                "kubectl_missing",
            )
            require(
                args.kubeconfig.is_file() and args.controller_kubeconfig.is_file(),
                "fixture_kubeconfigs_missing",
            )
        config = settings(args.settings)
        api = API(args.api, operator_tokens(args.operator_token_file, Keycloak(config)))
        other = None
        if not smoke:
            other = API(args.api, Tokens(private_text(args.other_token_file).strip()))
            # Validate prerequisites before creating a project. Never silently skip
            # authorization/audit coverage because an optional token was omitted.
            other.request("GET", "/projects")
        fixture = Fixture(args, api)
        error = None
        try:
            fixture.provision()
            from .security import check_access_and_audit, check_edge

            check_edge(fixture, config, smoke)
            if not smoke:
                from .logs import check_logs
                from .retirement import check_retirement
                from .state import check_configuration, check_secrets

                check_configuration(fixture)
                values = check_secrets(fixture)
                check_logs(fixture)
                check_access_and_audit(fixture, other, values)
                check_retirement(fixture)
        except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 -- sanitize dependency failures at CLI boundary
            error = (
                str(exc)
                if isinstance(exc, DrillError)
                else "dependency_or_assertion_failure"
            )
        try:
            fixture.retire()
        except (Exception, KeyboardInterrupt):  # noqa: BLE001 -- persist failed cleanup for operator review
            fixture.report["cleanup"] = "incomplete-manual-review-required"
        fixture.report.update(
            result="failed"
            if error or fixture.report["cleanup"].startswith("incomplete")
            else "passed",
            finishedAt=utc(),
        )
        if error:
            fixture.report["errorCode"] = error
        fixture.save()
        print("REPORT " + str(fixture.output / "report.json"), flush=True)
        return int(fixture.report["result"] != "passed")
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 -- sanitize dependency failures at CLI boundary
        print(
            "FAIL "
            + (str(exc) if isinstance(exc, DrillError) else "invalid_prerequisites")
        )
        return 1
