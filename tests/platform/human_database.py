"""Opt-in live acceptance for named human PostgreSQL access.

Only fixed, non-secret check names and run-scoped project names enter evidence.
The run never deploys the platform or automatically purges SQL data.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import psycopg

from .harness import API, DrillError, Keycloak, ROOT, operator_tokens, origin, private_text, require, settings, wait_for


RUN_ID = re.compile(r"^[0-9a-f]{12}$")
IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$")
CHECKS = (
    "isolated-bastion-configuration", "human-platform-administrator", "two-ready-project-databases",
    "ungranted-key-denied", "automation-credential-denied", "human-grant-and-distinct-credential",
    "authorized-tunnel", "read-only-own-database", "foreign-project-denied",
    "revocation-terminates-session", "revoked-login-denied", "revoked-key-denied",
    "redacted-audit-trail", "test-persona-revoked",
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_names(run_id: str) -> tuple[str, str]:
    require(bool(RUN_ID.fullmatch(run_id)), "invalid_run_id")
    return "hd-" + run_id + "-a", "hd-" + run_id + "-b"


def declaration(project: str, image: str, run_id: str, binding_id: str | None = None) -> dict:
    require(bool(IMAGE.fullmatch(image)), "digest_pinned_fixture_image_required")
    return {"apiVersion": "platform.example/v1alpha2", "kind": "Application",
        "metadata": {"name": project, "project": project}, "spec": {
            "components": [{"name": "api", "type": "service",
                "bindings": [{"bindingId": binding_id}] if binding_id else [],
                "runtime": {"type": "container", "image": image},
                "ports": [{"name": "http", "protocol": "http", "port": 8080}],
                "replicas": 1, "exposure": "private",
                "health": {"readiness": {"path": "/health/ready"}},
                "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                              "limits": {"cpu": "500m", "memory": "256Mi"}}}],
            "configuration": {"values": {"ACCEPTANCE_RUN_ID": run_id, "FIXTURE_ROLE": "database"}}}}


def validate(args) -> None:
    args.api = origin(args.api)
    project_names(args.run_id)
    require(bool(args.fixture_image and IMAGE.fullmatch(args.fixture_image)), "digest_pinned_fixture_image_required")
    try:
        address = ipaddress.ip_address(args.bastion_host)
    except ValueError:
        raise DrillError("bastion_ip_required") from None
    require(address.version == 4 and (address.is_private or address.is_loopback), "private_bastion_ip_required")
    require(1024 <= args.bastion_port <= 65535, "invalid_bastion_port")
    if args.command == "run":
        require(args.confirm_environment == args.api, "explicit_environment_confirmation_required")
        require(args.operator_token_file is not None and args.known_hosts_file is not None,
                "protected_session_and_host_key_required")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("plan", "run"))
    result.add_argument("--api", default="http://127.0.0.1:8000")
    result.add_argument("--run-id", required=True)
    result.add_argument("--fixture-image", required=True)
    result.add_argument("--bastion-host", default="127.0.0.1")
    result.add_argument("--bastion-port", type=int, default=2222)
    result.add_argument("--confirm-environment")
    result.add_argument("--operator-token-file", type=Path)
    result.add_argument("--known-hosts-file", type=Path)
    result.add_argument("--settings", type=Path, default=ROOT / ".env")
    return result


class Report:
    def __init__(self, run_id: str, api: str, image: str):
        project_a, project_b = project_names(run_id)
        parent = ROOT / ".runtime/human-database-access"
        require(not parent.is_symlink(), "unsafe_report_parent")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(stat.S_IMODE(parent.stat().st_mode) & 0o077 == 0, "unsafe_report_parent_permissions")
        self.directory = parent / run_id
        require(not self.directory.exists() and not self.directory.is_symlink(), "run_directory_exists")
        self.directory.mkdir(mode=0o700)
        self.data = {"format": 1, "runId": run_id, "api": api, "fixtureImage": image,
            "projects": [project_a, project_b], "startedAt": utc(), "result": "running",
            "gateClosed": False, "checks": [], "projectsRetained": True,
            "deferred": ["portal-browser-journey", "remote-firewall-reachability", "manual-evidence-review"]}
        self.save()

    def save(self) -> None:
        path = self.directory / "report.json"
        require(not path.is_symlink(), "unsafe_report_file")
        temporary = self.directory / (".report." + os.urandom(8).hex())
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(self.data, output, indent=2)
            output.write("\n")
        os.replace(temporary, path)

    def check(self, name: str, passed: bool) -> None:
        require(name in CHECKS, "unknown_check_name")
        self.data["checks"].append({"name": name, "result": "passed" if passed else "failed", "at": utc()})
        self.save()
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        require(passed, name)


def ssh_command(key: Path, known_hosts: Path, host: str, port: int, local_port: int,
                destination: str) -> list[str]:
    return ["ssh", "-F", "/dev/null", "-N", "-i", str(key), "-p", str(port),
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + str(known_hosts), "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=5", "-L", f"127.0.0.1:{local_port}:{destination}",
        "platform-db@" + host]


def unused_local_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop_tunnel(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def denied_ssh(command: list[str]) -> bool:
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return process.wait(timeout=12) != 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        stop_tunnel(process)


def ready_tunnel(process: subprocess.Popen, port: int, seconds: int = 15) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def assert_bastion_config(config_path: Path, destination: str) -> None:
    require(config_path.is_file() and not config_path.is_symlink(), "bastion_configuration_missing")
    check = subprocess.run(["/usr/sbin/sshd", "-T", "-f", str(config_path)],
                           capture_output=True, text=True, timeout=10)
    require(check.returncode == 0, "bastion_configuration_invalid")
    effective = set(check.stdout.lower().splitlines())
    for setting in ("allowtcpforwarding local", "permitopen " + destination,
                    "passwordauthentication no", "kbdinteractiveauthentication no",
                    "permittty no", "maxsessions 0", "authorizedkeysfile none"):
        require(setting in effective, "bastion_restriction_missing")


def wait_deployment(api: API, accepted: dict, seconds: int = 240) -> None:
    path = accepted.get("status_url")
    require(isinstance(path, str) and bool(re.fullmatch(r"/v1/operations/[0-9a-f-]+", path)),
            "invalid_operation_url")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = api.request("GET", path)
        require(current.get("state") != "failed", "fixture_deployment_failed")
        readiness = current.get("readiness") or {}
        if current.get("state") == "succeeded" and readiness.get("state") == "ready":
            return
        time.sleep(2)
    raise DrillError("fixture_readiness_timeout")


class Drill:
    def __init__(self, args, config: dict, api: API, report: Report):
        self.args, self.config, self.api, self.report = args, config, api, report
        self.project_a, self.project_b = project_names(args.run_id)
        self.grant_id = None
        self.resources = {}
        self.grant_requested = False
        self.grant_revoked = False
        self.persona_id = None
        self.persona_creation_attempted = False
        self.persona_revoked = False
        self.started = datetime.now(timezone.utc)
        self.tunnel = None
        self.sql_connection = None
        self.human_issuer = None
        self.human_subject = None

    def human_identity(self) -> tuple[str, str]:
        # API verifies this token before it is used for any mutation. Decoding
        # without a signature here only selects the same identity for a grant.
        claims = jwt.decode(self.api.tokens.get(), options={"verify_signature": False,
            "verify_aud": False, "verify_exp": False})
        issuer, subject = claims.get("iss"), claims.get("sub")
        require(isinstance(issuer, str) and bool(issuer) and isinstance(subject, str)
                and bool(subject), "operator_identity_missing")
        return issuer.rstrip("/"), subject

    def api_status(self, method: str, path: str, body=None, token: str | None = None) -> int:
        require(path.startswith("/") and not path.startswith("//"), "invalid_api_path")
        response = self.api.http.request(method, self.api.url + path, json=body,
            headers={"Authorization": "Bearer " + (token or self.api.tokens.get())})
        return response.status_code

    def preflight(self) -> None:
        require(os.geteuid() == 0, "root_runner_required")
        for executable in ("ssh", "ssh-keygen"):
            require(shutil.which(executable) is not None, "ssh_client_missing")
        require(Path("/usr/sbin/sshd").is_file(), "sshd_missing")
        require(self.args.known_hosts_file is not None, "known_hosts_required")
        private_text(self.args.known_hosts_file)
        host_key = subprocess.run(["ssh-keygen", "-F",
            f"[{self.args.bastion_host}]:{self.args.bastion_port}",
            "-f", str(self.args.known_hosts_file)], capture_output=True, timeout=5)
        require(host_key.returncode == 0, "trusted_bastion_host_key_missing")
        postgres_ip = self.config.get("STORE_RELAY_IP", "172.30.80.15")
        try:
            require(isinstance(postgres_ip, str) and ipaddress.ip_address(postgres_ip).version == 4,
                    "postgres_ip_missing")
        except ValueError:
            raise DrillError("postgres_ip_missing") from None
        self.relay_ip = postgres_ip
        self.destination = postgres_ip + ":*"
        assert_bastion_config(Path("/etc/ssh/sshd_config_platform_db"), self.destination)
        self.report.check("isolated-bastion-configuration", True)
        self.api.request("GET", "/platform/test-runner-credentials")
        self.human_issuer, self.human_subject = self.human_identity()
        current_access = self.api.request("GET", "/v1/store-access/me")
        require(not current_access.get("grants") and current_access.get("key_fingerprint") is None,
            "dedicated_human_without_existing_store_access_required")
        self.report.check("human-platform-administrator", True)
        for project in (self.project_a, self.project_b):
            require(self.api_status("GET", f"/projects/{project}/revisions") == 404,
                    "run_project_name_in_use")
        identities = self.api.request("GET", "/platform/test-identities?test_run_id=" + self.args.run_id)
        require(identities.get("credentials") == [], "run_test_identity_name_in_use")

    def deploy_projects(self) -> None:
        for project in (self.project_a, self.project_b):
            self.api.request("POST", "/projects", {"name": project}, statuses=(201,))
            resource = self.api.request("POST", "/v1/projects/" + project + "/resources",
                {"name": "state", "provider": "postgresql"}, statuses=(202,))
            self.resources[project] = resource["resource_id"]
            wait_for(lambda: self.api.request("GET", "/v1/resources/" + resource["resource_id"])["observed_state"] == "active",
                "named_database_not_ready")
            binding = self.api.request("POST", "/v1/projects/" + project + "/resource-bindings",
                {"resource_id": resource["resource_id"], "component": "api", "mode": "read-write"}, statuses=(202,))
            wait_for(lambda: any(g["grant_id"] == binding["grant_id"] and g["observed_state"] == "active"
                for g in self.api.request("GET", "/v1/projects/" + project + "/resource-bindings")["bindings"]),
                "named_binding_not_ready")
            accepted = self.api.request("PUT", "/projects/" + project,
                declaration(project, self.args.fixture_image, self.args.run_id, binding["grant_id"]), etag=0, statuses=(202,))
            wait_deployment(self.api, accepted)
        self.report.check("two-ready-project-databases", True)

    def machine_denial(self, key: str) -> None:
        self.persona_creation_attempted = True
        created = self.api.request("POST", "/platform/test-identities", {
            "name": "human-db-denial-" + self.args.run_id,
            "role": "project-admin", "project": self.project_a,
            "test_run_id": self.args.run_id, "expires_in_hours": 2,
        }, statuses=(201,))
        self.persona_id = created.get("credential_id")
        require(isinstance(self.persona_id, str) and bool(self.persona_id), "test_persona_missing")
        endpoint = created.get("token_endpoint")
        expected_issuer = self.config.get("OIDC_ISSUER") or (
            "https://" + self.config["IDENTITY_DOMAIN"] + "/realms/platform")
        require(endpoint == expected_issuer.rstrip("/") + "/protocol/openid-connect/token",
                "untrusted_token_endpoint")
        response = self.api.http.post(endpoint, data={
            "grant_type": "client_credentials", "client_id": created["client_id"],
            "client_secret": created["client_secret"]})
        require(response.status_code == 200, "test_persona_token_unavailable")
        token = response.json().get("access_token")
        require(isinstance(token, str) and bool(token), "test_persona_token_missing")
        denied = self.api_status("POST", "/v1/store-access/00000000-0000-0000-0000-000000000000/credentials", token=token)
        self.report.check("automation-credential-denied", denied == 403)

    def check_sql(self, username: str, password: str, port: int) -> None:
        connection_args = {"host": "127.0.0.1", "port": port, "user": username,
                           "password": password, "connect_timeout": 5}
        self.sql_connection = psycopg.connect(**connection_args, dbname="resource_" + self.resources[self.project_a].replace("-", ""),
                                              autocommit=True)
        own_database = "resource_" + self.resources[self.project_a].replace("-", "")
        own = self.sql_connection.execute("SELECT current_database(), current_user").fetchone()
        marker = self.sql_connection.execute("SELECT marker FROM acceptance_state WHERE id=1").fetchone()
        read_ok = own == (own_database, own_database + "_reader") and marker == ("database-" + self.args.run_id,)
        for statement in ("INSERT INTO acceptance_state(id, marker) VALUES (2, 'denied')",
                          "CREATE TABLE human_access_probe (id integer)"):
            with psycopg.connect(**connection_args, dbname=own_database) as denied_connection:
                try:
                    denied_connection.execute(statement)
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    read_ok = False
                finally:
                    denied_connection.rollback()
        self.report.check("read-only-own-database", read_ok)
        try:
            with psycopg.connect(**connection_args,
                                 dbname="resource_" + self.resources[self.project_b].replace("-", "")):
                foreign_denied = False
        except psycopg.OperationalError:
            foreign_denied = True
        # A live own-project session is the positive control for the denial.
        still_live = self.tunnel is not None and self.tunnel.poll() is None and self.sql_connection.execute(
            "SELECT 1").fetchone() == (1,)
        self.report.check("foreign-project-denied", foreign_denied and still_live)

    def run(self) -> None:
        self.preflight()
        self.deploy_projects()
        with tempfile.TemporaryDirectory(prefix="human-db-", dir=self.report.directory) as temporary:
            key_path = Path(temporary) / "id_ed25519"
            generated = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
                                       capture_output=True, timeout=15)
            require(generated.returncode == 0, "ephemeral_key_generation_failed")
            fields = key_path.with_suffix(".pub").read_text(encoding="ascii").split()
            require(len(fields) >= 2 and fields[0] == "ssh-ed25519", "ephemeral_key_invalid")
            public_key = " ".join(fields[:2])
            local_port = unused_local_port()
            command = ssh_command(key_path, self.args.known_hosts_file, self.args.bastion_host,
                                  self.args.bastion_port, local_port, self.relay_ip + ":20000")
            self.report.check("ungranted-key-denied", denied_ssh(command))
            self.machine_denial(public_key)
            self.api.request("PUT", "/v1/store-access/me/key", {"public_key": public_key})
            self.grant_requested = True
            grant = self.api.request("POST", "/v1/resources/" + self.resources[self.project_a] + "/human-grants",
                {"issuer": self.human_issuer, "subject": self.human_subject, "mode": "read-only"}, statuses=(202,))
            self.grant_id = grant["grant_id"]
            lease = self.api.request("POST", "/v1/store-access/" + self.grant_id + "/credentials", statuses=(202,))
            credential = None
            def credential_ready():
                nonlocal credential
                credential = self.api.request("GET", "/v1/store-access/credentials/" + lease["credential_id"], statuses=(200,202))
                return credential.get("state") == "active" and "connection" in credential
            wait_for(credential_ready, "human_credential_not_ready")
            connection = credential["connection"]
            username, password = connection["PGUSER"], connection["PGPASSWORD"]
            workload_role = "resource_" + self.resources[self.project_a].replace("-", "")
            valid = (grant["mode"] == "read-only" and grant["state"] == "active"
                and isinstance(password, str) and len(password) >= 32 and username.startswith("credential_")
                and connection["PGDATABASE"] == workload_role
                and 86390 <= (datetime.fromisoformat(lease["expires_at"]) - datetime.fromisoformat(lease["issued_at"])).total_seconds() <= 86400)
            self.report.check("human-grant-and-distinct-credential", valid)
            self.destination = self.relay_ip + ":" + connection["PGPORT"]
            command = ssh_command(key_path, self.args.known_hosts_file, self.args.bastion_host,
                self.args.bastion_port, local_port, self.destination)
            self.tunnel = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                self.report.check("authorized-tunnel", ready_tunnel(self.tunnel, local_port))
                self.check_sql(username, password, local_port)
                self.api.request("POST", "/v1/resource-grants/" + self.grant_id + "/revocation",
                                 {"version": grant["version"]}, statuses=(202,))
                self.grant_revoked = True
                terminated = False
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        self.sql_connection.execute("SELECT 1")
                    except (psycopg.OperationalError, psycopg.InterfaceError):
                        terminated = True
                        break
                    time.sleep(0.2)
                self.report.check("revocation-terminates-session",
                                  terminated and self.tunnel.poll() is None)
                try:
                    with psycopg.connect(host="127.0.0.1", port=local_port, user=username,
                                         password=password, dbname=workload_role, connect_timeout=5):
                        new_denied = False
                except psycopg.OperationalError:
                    new_denied = True
                self.report.check("revoked-login-denied", new_denied and self.tunnel.poll() is None)
            finally:
                if self.sql_connection is not None:
                    self.sql_connection.close()
                stop_tunnel(self.tunnel)
                self.tunnel = None
            self.report.check("revoked-key-denied", denied_ssh(command))
            self.audit(password, public_key)

    def audit(self, password: str, public_key: str) -> None:
        start = (self.started - timedelta(minutes=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        query = urlencode({"start": start, "end": end, "limit": 10000})
        result = self.api.request("GET", "/operator/audit/events?" + query)
        events = result.get("events")
        require(isinstance(events, list), "audit_export_invalid")
        scoped = [event for event in events if isinstance(event, dict)
                  and isinstance(event.get("scope"), dict)
                  and event["scope"].get("project") == self.project_a
                  and event.get("result") == "succeeded"]
        actions = {event.get("action") for event in scoped}
        required = {"store.human-grant", "store.credential-reveal", "store.grant-revoke"}
        encoded = json.dumps(events)
        secret_free = password not in encoded and public_key not in encoded
        self.report.check("redacted-audit-trail", required <= actions and secret_free)

    def cleanup(self) -> bool:
        success = True
        if self.grant_requested and not self.grant_revoked:
            try:
                rows = self.api.request("GET", "/v1/resources/" + self.resources[self.project_a] + "/grants")["grants"]
                for row in rows:
                    if (row["kind"] == "human" and row["issuer"] == self.human_issuer
                            and row["subject"] == self.human_subject and row["state"] == "active"):
                        self.api.request("POST", "/v1/resource-grants/" + row["grant_id"] + "/revocation",
                            {"version": row["version"]}, statuses=(202,))
                self.grant_revoked = True
            except Exception:
                success = False
        if self.persona_creation_attempted and not self.persona_revoked:
            try:
                credentials = self.api.request("GET", "/platform/test-identities?test_run_id=" + self.args.run_id)
                records = credentials.get("credentials")
                require(isinstance(records, list), "test_persona_list_invalid")
                for record in records:
                    require(record.get("test_run_id") == self.args.run_id and
                            record.get("name") == "human-db-denial-" + self.args.run_id and
                            record.get("project") == self.project_a, "unexpected_test_persona")
                    if record.get("status") != "revoked":
                        result = self.api.request("DELETE", "/platform/test-identities/" + record["credential_id"],
                                                  statuses=(200, 202))
                        require(result.get("status") == "revoked", "test_persona_revocation_pending")
                self.persona_revoked = True
                success = success and self.persona_revoked
            except Exception:
                success = False
        if self.persona_creation_attempted:
            self.report.check("test-persona-revoked", self.persona_revoked)
        return success


def main(argv=None) -> int:
    report = None
    try:
        args = parser().parse_args(argv)
        validate(args)
        if args.command == "plan":
            print(json.dumps({"format": 1, "runId": args.run_id, "mutates": False,
                "projects": list(project_names(args.run_id)), "fixtureImage": args.fixture_image,
                "checks": list(CHECKS), "projectsRetainedAfterRun": True,
                "gateClosed": False}, indent=2))
            return 0
        config = settings(args.settings)
        keycloak = Keycloak(config)
        api = API(args.api, operator_tokens(args.operator_token_file, keycloak))
        report = Report(args.run_id, args.api, args.fixture_image)
        drill = Drill(args, config, api, report)
        error = None
        try:
            drill.run()
        except (Exception, KeyboardInterrupt) as exc:
            error = str(exc) if isinstance(exc, DrillError) else (
                "interrupted" if isinstance(exc, KeyboardInterrupt) else "dependency_failure")
        try:
            cleaned = drill.cleanup()
        except (Exception, KeyboardInterrupt):
            cleaned = False
        report.data.update(result="failed" if error or not cleaned else "core-passed", finishedAt=utc(),
                           cleanup="complete" if cleaned else "incomplete-retry-required")
        if error:
            report.data["errorCode"] = error
        report.save()
        print("REPORT " + str(report.directory / "report.json"), flush=True)
        print("Projects are retained; Phase 9 acceptance remains open.", flush=True)
        return 0 if not error and cleaned else 1
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, DrillError) else (
            "interrupted" if isinstance(exc, KeyboardInterrupt) else "configuration_or_dependency_failure")
        if report is not None:
            report.data.update(result="failed", finishedAt=utc(), errorCode=code)
            report.save()
        print("ERROR " + code, flush=True)
        return 1
