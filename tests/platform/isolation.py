"""Opt-in isolation acceptance using two named-store web/PostgreSQL projects."""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

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
from .data_preservation import web_postgres_declaration, project_row

# The probe prints only booleans. It never returns connection settings or SQL errors.
PROBE = """
import json, os, socket, sys, urllib.request
import psycopg
own, foreign, service, mode = sys.argv[1:]
if mode == 'peer':
    with urllib.request.urlopen('http://' + service + ':8080/health/ready', timeout=5) as response:
        assert response.status == 200
    print(json.dumps({'peerServiceReady': True}))
else:
    with psycopg.connect(connect_timeout=5) as conn:
        assert conn.execute('SELECT current_database()').fetchone()[0] == own
        assert conn.execute('SELECT 1').fetchone()[0] == 1
    denied = {}
    for name, database in (('foreignDatabaseDenied', foreign), ('platformDatabaseDenied', 'platform')):
        try:
            with psycopg.connect(dbname=database, connect_timeout=5):
                denied[name] = False
        except psycopg.OperationalError:
            denied[name] = True
    socket.getaddrinfo(service, 8080)
    for name, address, port in (('foreignServiceDenied', service, 8080),
                                ('publicEndpointDenied', '1.1.1.1', 443)):
        try:
            with socket.create_connection((address, port), timeout=5):
                denied[name] = False
        except OSError:
            denied[name] = True
    print(json.dumps({'ownDatabaseReady': True, 'foreignServiceDnsReady': True, **denied}))
"""
CHECKS = (
    "peer-service-ready",
    "own-database-ready",
    "foreign-database-denied",
    "platform-database-denied",
    "foreign-service-dns-ready",
    "foreign-service-denied",
    "public-endpoint-denied",
)


def project_names(run_id):
    require(bool(RUN_ID.fullmatch(run_id)), "invalid_run_id")
    return "iso-" + run_id + "-a", "iso-" + run_id + "-b"


def declaration(project, image, run_id, binding_id):
    require(project in project_names(run_id), "invalid_fixture_project")
    return web_postgres_declaration(project, image, run_id, binding_id, "500m")


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
    result.add_argument("--operator-token-file", type=Path)
    result.add_argument("--settings", type=Path, default=ROOT / ".env")
    result.add_argument("--kubectl", type=Path, default=ROOT / ".runtime/bin/kubectl")
    result.add_argument(
        "--kubeconfig", type=Path, default=ROOT / ".runtime/admin.kubeconfig"
    )
    return result


def validate(args):
    args.api = origin(args.api)
    project_names(args.run_id)
    require(
        bool(IMAGE.fullmatch(args.fixture_image)),
        "digest_pinned_fixture_image_required",
    )
    if args.command == "run":
        require(
            args.confirm_environment == args.api,
            "explicit_environment_confirmation_required",
        )
        require(args.operator_token_file is not None, "operator_token_file_required")


class Report:
    def __init__(self, run_id, api, image):
        parent = ROOT / ".runtime/isolation"
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
            "projects": list(project_names(run_id)),
            "startedAt": utc(),
            "result": "running",
            "createAttempted": [],
            "created": [],
            "resources": {},
            "bindings": {},
            "checks": [],
            "cleanup": "pending",
            "databasesRetained": True,
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


def probe(kubectl, kubeconfig, project, own, foreign, peer_service, mode):
    command = [
        str(kubectl),
        "--kubeconfig",
        str(kubeconfig),
        "-n",
        "project-" + project,
        "exec",
        "deployment/web",
        "--",
        "python",
        "-c",
        PROBE,
        own,
        foreign,
        peer_service,
        mode,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        require(result.returncode == 0, "fixture_probe_failed")
        payload = json.loads(result.stdout)
        require(
            isinstance(payload, dict)
            and set(payload)
            == (
                {"peerServiceReady"}
                if mode == "peer"
                else {
                    "ownDatabaseReady",
                    "foreignServiceDnsReady",
                    "foreignDatabaseDenied",
                    "platformDatabaseDenied",
                    "foreignServiceDenied",
                    "publicEndpointDenied",
                }
            )
            and all(isinstance(value, bool) for value in payload.values()),
            "invalid_probe_result",
        )
        return payload
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise DrillError("fixture_probe_failed") from None


def deploy(api, report, project, image, run_id):
    report.data["createAttempted"].append(project)
    report.save()
    api.request("POST", "/projects", {"name": project}, statuses=(201,))
    report.data["created"].append(project)
    report.save()
    resource = api.request(
        "POST",
        "/v1/projects/" + project + "/resources",
        {"name": "state", "provider": "postgresql"},
        statuses=(202,),
    )
    resource_id = resource["resource_id"]
    report.data["resources"][project] = resource_id
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
    report.data["bindings"][project] = binding_id
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
        declaration(project, image, run_id, binding_id),
        etag=0,
        statuses=(202,),
    )
    wait_deployment(api, accepted)


def run(args, api, report):
    require(
        args.kubectl.is_file() and os.access(args.kubectl, os.X_OK), "kubectl_missing"
    )
    require(
        args.kubeconfig.is_file() and not args.kubeconfig.is_symlink(),
        "kubeconfig_missing",
    )
    api.request("GET", "/platform/test-context")
    project_a, project_b = project_names(args.run_id)
    for project in (project_a, project_b):
        require(project_row(api, project) is None, "run_project_name_in_use")
    for project in (project_a, project_b):
        deploy(api, report, project, args.fixture_image, args.run_id)
    database_a = "resource_" + report.data["resources"][project_a].replace("-", "")
    database_b = "resource_" + report.data["resources"][project_b].replace("-", "")
    service_b = "web.project-" + project_b + ".svc.cluster.local"
    peer = probe(
        args.kubectl,
        args.kubeconfig,
        project_b,
        database_b,
        database_a,
        service_b,
        "peer",
    )
    report.check("peer-service-ready", peer["peerServiceReady"])

    def isolated():
        try:
            result = probe(
                args.kubectl,
                args.kubeconfig,
                project_a,
                database_a,
                database_b,
                service_b,
                "isolation",
            )
        except DrillError:
            return None
        return result if all(result.values()) else None

    results = wait_for(isolated, "isolation_not_observed", 90)
    for name, key in (
        ("own-database-ready", "ownDatabaseReady"),
        ("foreign-database-denied", "foreignDatabaseDenied"),
        ("platform-database-denied", "platformDatabaseDenied"),
        ("foreign-service-dns-ready", "foreignServiceDnsReady"),
        ("foreign-service-denied", "foreignServiceDenied"),
        ("public-endpoint-denied", "publicEndpointDenied"),
    ):
        report.check(name, results[key])


def retire(api, report):
    names = set(report.data["projects"])
    require(
        set(report.data["created"]) <= names
        and set(report.data["createAttempted"]) <= names,
        "cleanup_scope_mismatch",
    )
    complete = True
    for project in reversed(report.data["projects"]):
        if (
            project in report.data["createAttempted"]
            and project not in report.data["created"]
        ):
            complete = False  # A lost create response does not prove ownership.
            continue
        if project not in report.data["created"]:
            continue
        try:
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
                preview = api.request(
                    "GET", "/projects/" + project + "/retirement-preview"
                )
                require(not preview["blockers"], "cleanup_retirement_blocked")
                confirmation = {
                    "confirm_name": project,
                    "scope_token": preview["scope_token"],
                }
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
        except (Exception, KeyboardInterrupt):
            complete = False
    report.data["cleanup"] = (
        "retired-data-retained"
        if complete and report.data["created"]
        else ("not-needed" if complete else "incomplete-retry-required")
    )
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
                        "projects": list(project_names(args.run_id)),
                        "fixtureImage": args.fixture_image,
                        "checks": list(CHECKS),
                        "retireAfterRun": True,
                        "databasesRetained": True,
                    },
                    indent=2,
                )
            )
            return 0
        api = API(
            args.api,
            operator_tokens(
                args.operator_token_file, Keycloak(settings(args.settings))
            ),
        )
        report = Report(args.run_id, args.api, args.fixture_image)
        error = None
        try:
            run(args, api, report)
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
        try:
            retire(api, report)
        except (Exception, KeyboardInterrupt):
            report.data["cleanup"] = "incomplete-retry-required"
            report.save()
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
